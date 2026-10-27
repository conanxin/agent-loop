#!/usr/bin/env python3
"""Derive a sanitized B3-R2 stage receipt from immutable run metadata and blind judge.

No model calls. Does not infer quality from failed runs. The blind judge is an
independent Hermes MODEL, not an independent human, and returns PARTIAL where
the owner-override intent is not demonstrated by the provided snippets.
"""
from pathlib import Path
import argparse
import json

from score_delivery import metrics

VALID={"SUPPORTED","PARTIAL","UNSUPPORTED","UNCERTAIN"}

def build(root, results, full, low, blind):
    study=metrics(root,"compact_adaptive",results)
    observed=[x for x in study["runs"] if x["status"]!="NOT_RUN"]
    original={}
    for label,folder in (("full_context",full),("compact_unsupported_low",low)):
        rows=[]
        if folder.is_dir():
            for file in sorted(folder.glob("*.json")):
                if file.name.endswith("metrics.json"):continue
                d=json.loads(file.read_text(encoding="utf-8"))
                if not isinstance(d,dict) or "arm" not in d:continue
                rows.append({"case":d.get("case"),"arm":d["arm"],
                             "status":d.get("status"),"seconds":d.get("seconds"),
                             "model_result_delivered":d.get("status")=="COMPLETED"})
        original[label]=rows
    judge=json.loads((blind/"protocol-implementation.judge_result.json").read_text())
    aliases=json.loads((blind/"mapping.private.json").read_text())
    decisions=[]
    for opinion in judge.get("judgments",[]):
        fid=opinion.get("blind_id")
        target=aliases.get(fid)
        if not target:raise ValueError("unmapped judge finding")
        cid,rep,arm,index=target.split("|")
        verdict=opinion.get("verdict")
        if verdict not in VALID:raise ValueError("invalid judge verdict")
        decisions.append({"case":cid,"repeat":rep,"arm":arm,
                          "finding_index":int(index),"verdict":verdict,
                          "issue_cluster":str(opinion.get("cluster",""))[:100],
                          "evidence_reason":str(opinion.get("why",""))[:600]})
    if len(decisions)!=4:
        raise ValueError("blinded judge returned incomplete result; do not publish as fully graded")
    return {
      "schema":"egm.b3r2.stage_receipt/1",
      "date":"2026-10-27",
      "source_commit":study["frozen_commit"],
      "source_unmodified":True,
      "experiment_conditions":{
          "full_context_first_pair":original["full_context"],
          "compact_unsupported_low_thinking":original["compact_unsupported_low"],
          "compact_adaptive": {
             "planned":len(study["runs"]),
             "attempted":len(observed),
             "delivered":sum(x["status"]=="COMPLETED" for x in observed),
             "timeouts":sum(x["status"]=="TIMEOUT" for x in observed),
             "not_attempted":sum(x["status"]=="NOT_RUN" for x in study["runs"]),
             "full_pairs_delivered":sum(x["both_delivered"] for x in study["pairs"]),
             "arm_summaries":study["arm_summary"],
             "case_receipts":[{"case":row["case"],"arm":row["arm"],
                               "repeat":row["repeat"],"status":row["status"],
                               "seconds":row.get("seconds"),"finding_count":row.get("finding_count")}
                              for row in observed]
          }
      },
      "blind_review":{
          "reviewer":"fresh-context local Hermes model; no arm names in judgment input",
          "human_blind_review":False,
          "case":"protocol-implementation",
          "judged_findings":len(decisions),
          "supported":sum(d["verdict"]=="SUPPORTED" for d in decisions),
          "partial":sum(d["verdict"]=="PARTIAL" for d in decisions),
          "unsupported":sum(d["verdict"]=="UNSUPPORTED" for d in decisions),
          "uncertain":sum(d["verdict"]=="UNCERTAIN" for d in decisions),
          "distinct_partial_clusters":len({d["issue_cluster"] for d in decisions if d["verdict"]=="PARTIAL"}),
          "assessments":decisions
      },
      "conclusion":{
          "valid_quality_pairs":1,
          "incremental_verified_goldfish_defects":0,
          "reliable_global_quality_comparison":False,
          "reason":"Only one paired case delivered; its two issue clusters were judged PARTIAL in both arms, and P6/P9 each timed out for both arms.",
          "adoption":"Keep single-agent default; opt-in independent Goldfish for high-risk designs only. Require reproducible verification before implementation.",
          "uncertainty":"Model execution reliability and unreviewed source context prevent generalizing quality uplift."
      },
      "limits":["No independent human blind grader","No replicated complete case pairs",
                "No verified USD charges","Full/compact/invalid-config conditions not pooled",
                "First case PARTIAL does not establish absence of any actual defect"],
    }

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-root",required=True)
    ap.add_argument("--results",required=True)
    ap.add_argument("--full",required=True)
    ap.add_argument("--low",required=True)
    ap.add_argument("--blind",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    obj=build(Path(args.source_root),Path(args.results),Path(args.full),
              Path(args.low),Path(args.blind))
    target=Path(args.out)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"attempted":obj["experiment_conditions"]["compact_adaptive"]["attempted"],
                      "delivered":obj["experiment_conditions"]["compact_adaptive"]["delivered"],
                      "timeouts":obj["experiment_conditions"]["compact_adaptive"]["timeouts"],
                      "judged":obj["blind_review"]["judged_findings"],
                      "partial":obj["blind_review"]["partial"],
                      "verified":obj["blind_review"]["supported"]},ensure_ascii=False))
