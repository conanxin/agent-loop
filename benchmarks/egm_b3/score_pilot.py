#!/usr/bin/env python3
"""Reproducible provisional anchor scoring for B3 lean pilot outputs.

NOT a blind human evaluation. True positive means a seeded assertion's line was
cited as the problem or its conflicting evidence; reviewers must inspect the
issue/rationale before treating this as a validated defect detection.
"""
from pathlib import Path
import argparse, json, re, statistics

BASE=Path(__file__).resolve().parent

def anchor_hit(findings, line):
    pattern=re.compile(r"(?<!\d)(?:L|行)?"+str(line)+r"(?!\d)")
    matched=[]
    for i,f in enumerate(findings):
        try:line_num=int(str(f.get("line")).lstrip("L"))
        except (TypeError,ValueError):line_num=-1
        combined=str(f.get("evidence",""))+" "+str(f.get("issue",""))
        if line_num==line or pattern.search(combined):
            matched.append(i)
    return matched

def evaluate(root):
    truth=json.loads((BASE/"ground_truth.json").read_text())
    pairs=[];all_rows=[]
    for item in truth["cases"]:
        case=item["id"]
        per={}
        for arm in ("baseline","goldfish"):
            p=root/f"{case}_{arm}.json"
            if not p.exists():
                per[arm]={"case":case,"arm":arm,"status":"MISSING"}
                continue
            d=json.loads(p.read_text())
            if d.get("source_sha256")!=item["fixture_sha256"]:
                raise ValueError(f"Wrong fixture version for {case}/{arm}")
            findings=d.get("findings",[])
            seeds=[{"id":z["id"],"line":z["line"],
                    "candidate_indices":anchor_hit(findings,z["line"])}
                   for z in item["seeded_faults"]]
            selected=set(i for z in seeds for i in z["candidate_indices"])
            extras=[{"index":i,"line":f.get("line"),"issue":str(f.get("issue",""))[:230]}
                    for i,f in enumerate(findings) if i not in selected]
            per[arm]={
               "case":case,"arm":arm,"status":d.get("status"),
               "seconds":d.get("elapsed_seconds"),
               "findings":len(findings),
               "provisional_seeded_hits":sum(bool(z["candidate_indices"]) for z in seeds),
               "seeded_total":len(seeds),
               "anchors":seeds,
               "additional_findings_not_yet_adjudicated":extras,
               "tokens":d.get("trace_meta",{}).get("usage_tokens",{}),
               "tool_calls":d.get("trace_meta",{}).get("tool_call_events"),
               "model_visible_tool_count":d.get("trace_meta",{}).get("tool_schema_count")
            }
            all_rows.append(per[arm])
        if all(per.get(a,{}).get("status")=="COMPLETED" for a in ("baseline","goldfish")):
            b,g=per["baseline"],per["goldfish"]
            pairs.append({
               "case":case,
               "baseline_provisional_hits":b["provisional_seeded_hits"],
               "goldfish_provisional_hits":g["provisional_seeded_hits"],
               "new_hits":g["provisional_seeded_hits"]-b["provisional_seeded_hits"],
               "baseline_time_s":b["seconds"],"goldfish_time_s":g["seconds"],
               "delta_time_s":round(g["seconds"]-b["seconds"],3),
               "baseline_total_tokens":b["tokens"].get("total"),
               "goldfish_total_tokens":g["tokens"].get("total"),
               "delta_total_tokens":(g["tokens"]["total"]-b["tokens"]["total"]) if
                  "total" in b["tokens"] and "total" in g["tokens"] else None
            })
    return {
        "schema":"egm.b3.lean_score/1",
        "type":"PROVISIONAL_SEEDED_ANCHOR",
        "manual_semantic_adjudication_required":True,
        "independent_human_blind_review_performed":False,
        "complete_pairs":len(pairs),
        "pairs":pairs,"all_arms":all_rows,
        "limitations":["Only planted contradictions in three source-derived fixtures",
                       "Anchor matching alone does not establish semantic correctness",
                       "One call per arm per case; one model; EGM-style prompt, not full EGM pipeline",
                       "Unmatched findings are NOT automatically false positives"]
    }

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    data=evaluate(Path(args.results))
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    print("COMPLETE_PAIRS",data["complete_pairs"])
    for item in data["pairs"]:print(item)
