#!/usr/bin/env python3
"""Generate sanitized, reproducible B3 results summary from local private receipts."""
from pathlib import Path
import argparse,json,statistics

HERE=Path(__file__).resolve().parent

def summarize(results):
    truth=json.loads((HERE/"ground_truth.json").read_text())
    adjud=json.loads((HERE/"adjudication.json").read_text())
    if len(truth["cases"])!=len(adjud["cases"]):
        raise ValueError("adjudication is not aligned with frozen cases")
    matrix=[]
    aggregates={}
    for case in truth["cases"]:
        row={"case":case["id"],"source_file":case["source_file"],
             "fixture_sha256":case["fixture_sha256"],
             "seeded_fault_count":len(case["seeded_faults"])}
        decisions=next(c for c in adjud["cases"] if c["case"]==case["id"])
        for arm in ("baseline","goldfish"):
            file=results/(case["id"]+"_"+arm+".json")
            model=json.loads(file.read_text(encoding="utf-8"))
            if model["source_sha256"]!=case["fixture_sha256"]:
                raise RuntimeError("source digest mismatch")
            if model.get("status")!="COMPLETED":
                raise RuntimeError("cannot score incomplete paired run")
            rulings=decisions[arm]
            if len(rulings)!=len(model.get("findings",[])):
                raise RuntimeError("manual finding tally differs from model")
            validids={c["id"] for c in case["seeded_faults"]}
            for r in rulings:
                if r["seed"] not in validids or r["verdict"] not in ("TP","FP","UNRESOLVED"):
                    raise RuntimeError("unknown adjudication")
            row[arm]={
                "status":model["status"],"elapsed_s":model["elapsed_seconds"],
                "total_tokens":model["trace_meta"]["usage_tokens"].get("total"),
                "input_tokens":model["trace_meta"]["usage_tokens"].get("input"),
                "output_tokens":model["trace_meta"]["usage_tokens"].get("output"),
                "tool_calls":model["trace_meta"].get("tool_call_events"),
                "model_visible_tool_schemas":model["trace_meta"].get("tool_schema_count"),
                "reported_findings":len(model.get("findings",[])),
                "adjudicated_tp":sum(r["verdict"]=="TP" for r in rulings),
                "adjudicated_fp":sum(r["verdict"]=="FP" for r in rulings),
                "session_id":model.get("session_id")
            }
        matrix.append(row)
    for arm in ("baseline","goldfish"):
        rs=[r[arm] for r in matrix]
        aggregates[arm]={
            "completed_runs":len(rs),"seeded_true_positives":sum(r["adjudicated_tp"] for r in rs),
            "confirmed_false_positives":sum(r["adjudicated_fp"] for r in rs),
            "total_reported_findings":sum(r["reported_findings"] for r in rs),
            "elapsed_s":round(sum(r["elapsed_s"] for r in rs),3),
            "median_elapsed_s":statistics.median(r["elapsed_s"] for r in rs),
            "total_tokens":sum(r["total_tokens"] for r in rs),
            "input_tokens":sum(r["input_tokens"] for r in rs),
            "output_tokens":sum(r["output_tokens"] for r in rs),
            "tool_calls":sum(r["tool_calls"] for r in rs)}
    b,g=aggregates["baseline"],aggregates["goldfish"]
    return {
      "schema":"egm.b3.results/1","study_type":"source-derived controlled seeded pilot",
      "benchmark_date":"2026-10-27",
      "comparison":"Same MiniMax M3.1 Flash, same case fixture, fresh isolated context, short JSON; prompt strategy differs",
      "run_order":"state baseline→Goldfish, schemas Goldfish→baseline, EGM baseline→Goldfish",
      "initial_long_parallel_condition":{
        "planned_runs":6,"cli_successful_deliveries":0,
        "trace_json_recoveries_not_delivered":2,
        "one_other_model_text_unparseable":1,
        "remaining_no_completed_model_text":3,
        "warning":"not a quality comparison; multiple execution variables differ"},
      "lean_matched_condition":{
        "planned_runs":6,"cli_successful_deliveries":6,
        "seeded_total":6,"cases":matrix,"aggregate":aggregates,
        "goldfish_incremental_seeded_hits":g["seeded_true_positives"]-b["seeded_true_positives"],
        "goldfish_extra_seconds":round(g["elapsed_s"]-b["elapsed_s"],3),
        "goldfish_extra_elapsed_percent":round((g["elapsed_s"]/b["elapsed_s"]-1)*100,2),
        "goldfish_extra_tokens":g["total_tokens"]-b["total_tokens"],
        "goldfish_extra_tokens_percent":round((g["total_tokens"]/b["total_tokens"]-1)*100,2)
      },
      "adjudication":"ChatGPT assistant evidence-based review, not independent human blind rating",
      "actual_billing_cost_usd":None,
      "model_quality_conclusion":"No observed seed-recall advantage in this easy three-case, one-model single-run experiment",
      "limitations":["Planted contradictions in excerpts, near end of text",
                     "One model per arm, no repeated-run variance or independent human blind scoring",
                     "One-call Goldfish prompting is not full Google EGM multi-stage flow",
                     "Does not quantify benefit for complex real unmodified production specs",
                     "First condition changed both concurrency and output length, so reliability difference is not causally isolated"]
    }

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--results",required=True)
    parser.add_argument("--out",required=True)
    x=parser.parse_args()
    record=summarize(Path(x.results))
    p=Path(x.out);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(record["lean_matched_condition"]["aggregate"],ensure_ascii=False))
