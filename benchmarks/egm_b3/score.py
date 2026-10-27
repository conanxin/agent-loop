#!/usr/bin/env python3
"""Offline B3 scorer. Seeded-line matches are PROVISIONAL, not final human labels.

Reads a predeclared ground truth and run result metadata. Never sends the answer
key to cloud inference. Unmatched findings are 'unadjudicated', not assumed false.
"""
from pathlib import Path
import argparse, collections, hashlib, json, re, statistics

HERE=Path(__file__).resolve().parent


def score(root):
    truth=json.loads((HERE/"ground_truth.json").read_text(encoding="utf-8"))
    cases={c["id"]:c for c in truth["cases"]}
    records=[]
    for cid,c in cases.items():
        for arm in ("baseline","goldfish"):
            f=root/f"{cid}_{arm}.json"
            if not f.exists():
                records.append({"case":cid,"arm":arm,"status":"MISSING"});continue
            run=json.loads(f.read_text(encoding="utf-8"))
            if run.get("fixture_sha256")!=c["fixture_sha256"]:
                raise ValueError(f"SHA mismatch in result {f}")
            findings=run.get("findings",[]) if isinstance(run.get("findings"),list) else []
            hits=[]
            extras=[]
            for fault in c["seeded_faults"]:
                matching=[]
                for i,item in enumerate(findings):
                    line=item.get("line")
                    try: numeric=int(line)
                    except (ValueError,TypeError):numeric=-1
                    text=str(item.get("evidence",""))+" "+str(item.get("issue",""))
                    if numeric==fault["line"] or re.search(r"(?:^|\D)L?"+str(fault["line"])+r"(?:\D|$)",text):
                        matching.append(i)
                hits.append({"seed":fault["id"],"line":fault["line"],
                             "provisional_found":bool(matching),
                             "candidate_findings":matching})
            matched={i for hit in hits for i in hit["candidate_findings"]}
            extras=[{"index":i,"line":f.get("line"),"issue":str(f.get("issue",""))[:300]}
                    for i,f in enumerate(findings) if i not in matched]
            u=run.get("trace",{}).get("usage_tokens",{})
            records.append({
                "case":cid,"arm":arm,"status":run.get("status"),
                "seconds":run.get("seconds"),
                "finding_count":len(findings),
                "provisional_seeded_hits":sum(x["provisional_found"] for x in hits),
                "seeded_count":len(hits),
                "provisional_hit_details":hits,
                "additional_findings_need_adjudication":extras,
                "tool_call_events":run.get("trace",{}).get("tool_call_events"),
                "model_visible_tool_schema":run.get("trace",{}).get("tool_schema_count"),
                "input_tokens":u.get("input"),"output_tokens":u.get("output"),
                "cache_read_tokens":u.get("cacheRead"),
                "total_tokens":u.get("total"),
                "observed_cost_fields":run.get("trace",{}).get("cost_fields"),
                "session_id":run.get("session_id"),
                "prompt_sha256":run.get("prompt_sha256")
            })
    aggs=[]
    for arm in ("baseline","goldfish"):
        rs=[r for r in records if r["arm"]==arm]
        ok=[r for r in rs if r.get("status")=="COMPLETED"]
        aggs.append({"arm":arm,"successful":len(ok),"planned":len(rs),
                     "provisional_seeded_hits":sum(r.get("provisional_seeded_hits",0) for r in ok),
                     "seeded_denominator":sum(r.get("seeded_count",0) for r in rs),
                     "total_findings":sum(r.get("finding_count",0) for r in ok),
                     "median_seconds":statistics.median(r["seconds"] for r in ok) if ok else None,
                     "sum_elapsed_seconds":sum(r["seconds"] for r in ok),
                     "sum_input_tokens":sum(r.get("input_tokens") or 0 for r in ok),
                     "sum_output_tokens":sum(r.get("output_tokens") or 0 for r in ok),
                     "sum_total_tokens":sum(r.get("total_tokens") or 0 for r in ok),
                     "token_coverage":sum(r.get("total_tokens") is not None for r in ok)})
    return {"schema":"egm.b3.provisional_scoring/1",
            "method":"seeded-line grounding only; requires semantic and false-positive manual adjudication",
            "blind_human_graded":False,
            "provisional_only":True,
            "cases":records,"arm_aggregates":aggs,
            "limitations":["A report citing seeded lines can still misunderstand the issue",
                           "Unmatched findings can be genuine pre-existing issues; not automatically false positives",
                           "Single cloud model single repeat per arm not a generalizable quality estimate"]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--results",required=True)
    parser.add_argument("--out",required=True)
    a=parser.parse_args()
    results=score(Path(a.results))
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for x in results["arm_aggregates"]:
        print(x)

if __name__=="__main__":main()
