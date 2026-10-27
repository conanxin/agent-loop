#!/usr/bin/env python3
"""Delivery/citation/token metrics for real unmodified-source B3-R2 experiment.

This never treats citation existence or number of model findings as quality.
Independent semantic grading is a separate pass.
"""
from pathlib import Path
import argparse
import json
import re
import statistics

TAG=re.compile(r"^([A-Za-z0-9_./-]+):L([1-9][0-9]*)$")

def metrics(root,variant="compact_adaptive",results_dir=None):
    mapping={
      "full":("manifest.json","runs"),
      "compact_low":("manifest_compact.json","runs_compact"),
      "compact_adaptive":("manifest_compact.json","runs_compact_adaptive")
    }
    mf,dirname=mapping[variant]
    m=json.loads((root/mf).read_text(encoding="utf-8"))
    rows=[]
    for case in m["cases"]:
        valid=set()
        for source in case["segments"]:
            valid.update(f"{source['path']}:L{n}" for n in range(source["start"],source["end"]+1))
        for rep in (1,2):
            for arm in ("baseline","goldfish"):
                file=(results_dir/f"{case['case_id']}_r{rep}_{arm}.json"
                      if results_dir else
                      root/dirname/case["case_id"]/f"repeat{rep}-{arm}"/"result.json")
                if not file.exists():
                    rows.append({"case":case["case_id"],"repeat":rep,"arm":arm,"status":"NOT_RUN"})
                    continue
                v=json.loads(file.read_text(encoding="utf-8"))
                if v["packet_sha256"]!=case["packet_sha256"]:raise ValueError("source SHA mismatch")
                findings=v.get("findings",[]) if isinstance(v.get("findings"),list) else []
                refs=[r for f in findings for r in f.get("source_refs",[]) if isinstance(r,str)]
                validref=sum(x in valid for x in refs)
                trace=v.get("trace",{})
                rows.append({
                    "case":case["case_id"],"repeat":rep,"arm":arm,
                    "status":v["status"],"seconds":v.get("seconds"),
                    "finding_count":len(findings),"source_refs":len(refs),
                    "valid_source_refs":validref,
                    "invalid_source_refs":len(refs)-validref,
                    "tokens":trace.get("tokens",{}),
                    "tool_calls":trace.get("tool_calls"),
                    "model_visible_tools":trace.get("tools"),
                    "prior_messages":trace.get("prior_messages"),
                    "session_id":v.get("session_id"),
                    "semantic_support_unverified":True,
                })
    arms={}
    for arm in ("baseline","goldfish"):
        allitems=[r for r in rows if r["arm"]==arm]
        ok=[r for r in allitems if r["status"]=="COMPLETED"]
        arms[arm]={
            "completed":len(ok),"planned":len(allitems),
            "total_model_findings_unverified":sum(r.get("finding_count",0) for r in ok),
            "valid_line_refs_not_semantic_proof":sum(r["valid_source_refs"] for r in ok),
            "bad_ref_count":sum(r["invalid_source_refs"] for r in ok),
            "total_seconds":round(sum(r["seconds"] for r in ok),3),
            "median_seconds":statistics.median([r["seconds"] for r in ok]) if ok else None,
            "total_tokens":sum(r["tokens"].get("total") or 0 for r in ok),
            "token_coverage":sum(r["tokens"].get("total") is not None for r in ok),
            "bad_state_or_failures":{s:sum(r["status"]==s for r in allitems)
                                     for s in sorted({r["status"] for r in allitems if r["status"]!="COMPLETED"})},
        }
    pairs=[]
    for case in m["cases"]:
        for rep in (1,2):
            a=next(x for x in rows if x["case"]==case["case_id"] and x["repeat"]==rep and x["arm"]=="baseline")
            b=next(x for x in rows if x["case"]==case["case_id"] and x["repeat"]==rep and x["arm"]=="goldfish")
            pairs.append({"case":case["case_id"],"repeat":rep,
                         "both_delivered":a["status"]==b["status"]=="COMPLETED",
                         "baseline_status":a["status"],"goldfish_status":b["status"]})
    return {"schema":"cxpan.egm_b3r2.delivery_metrics/1","variant":variant,
            "frozen_commit":m["revision"],"source_unmodified":True,
            "findings_quality_status":"REQUIRES_BLINDED_EVIDENCE_ADJUDICATION",
            "arm_summary":arms,"pairs":pairs,"runs":rows,
            "limitations":["No benchmark ground truth for unmodified real source",
                           "Citation range is structural; not semantic proof",
                           "One host/model may have different failure rates at longer context"]}

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--workspace",required=True)
    ap.add_argument("--variant",choices=["full","compact_low","compact_adaptive"],default="compact_adaptive")
    ap.add_argument("--output",required=True)
    ap.add_argument("--results",default=None)
    a=ap.parse_args()
    obj=metrics(Path(a.workspace),a.variant,Path(a.results) if a.results else None)
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(obj["arm_summary"],ensure_ascii=False))
    print("PAIRS_DELIVERED",sum(x["both_delivered"] for x in obj["pairs"]))
