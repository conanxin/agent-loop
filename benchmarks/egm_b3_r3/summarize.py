#!/usr/bin/env python3
"""Aggregate B3-R3 private model receipts into a sanitized, inspectable report.

No model/API calls. Reports distinct smoke vs full bounded review conditions
without pooling incompatible-thinking errors into inference failure.
"""
from pathlib import Path
import argparse
import json
import statistics

EXPECTED={
    "p6_m27_invalid":"egm-b3r3-p6-minimaxm27-20261027",
    "p6_m27_smoke":"egm-b3r3-p6-m27medium-20261027",
    "p9_m27_smoke":"egm-b3r3-p9-m27medium-20261027",
    "p6_flash_same_prompt":"egm-b3r3-p6-flashadaptive-20261027",
    "p6_m27_review":"egm-b3r3-p6-boundedm27-20261027",
    "p9_m27_review":"egm-b3r3-p9-boundedm27-20261027",
}


def summarize(receipt_dir, invariant):
    receipts={}
    for key,name in EXPECTED.items():
        p=receipt_dir/(name+".json")
        d=json.loads(p.read_text(encoding="utf-8"))
        trace=d.get("trace") or {}
        usage=trace.get("usage_tokens") or trace.get("tokens") or {}
        receipts[key]={
            "workflow":name,"case":d["case"],"status":d["status"],
            "requested_model":d.get("model") or d.get("requested_model"),
            "requested_thinking":d.get("thinking") or d.get("requested_thinking"),
            "actual_model":trace.get("actual_model") or d.get("actual_model") or trace.get("model_id"),
            "source_sha256":d["source_sha256"],
            "prompt_sha256":d["prompt_sha256"],
            "prompt_chars":d["prompt_chars"],
            "session_id":d.get("session_id"),
            "elapsed_seconds":d["elapsed_seconds"],
            "model_completed":trace.get("model_completed_event",trace.get("model_completed")),
            "prompt_submitted":trace.get("prompt_submitted_event",trace.get("prompt_submitted")),
            "model_visible_tools":trace.get("model_visible_tool_count",trace.get("model_visible_tools")),
            "tool_calls":trace.get("tool_call_events",trace.get("tool_calls")),
            "total_tokens":usage.get("total"),
            "cli_exit":d.get("raw_cli_exit",d.get("cli_exit")),
            "format":"bounded_review" if key.endswith("_review") else "smoke",
            "findings_count":len(d.get("findings",[])) if key.endswith("_review") else None,
            "report_parseable":d.get("report_parseable") if key.endswith("_review") else None,
            "findings_source_refs":[f.get("structurally_valid_refs",[]) for f in d.get("findings",[])]
             if key.endswith("_review") else None,
        }
    p6=receipts["p6_m27_smoke"]
    flash=receipts["p6_flash_same_prompt"]
    if p6["prompt_sha256"]!=flash["prompt_sha256"] or p6["source_sha256"]!=flash["source_sha256"]:
        raise ValueError("P6 short response controls did not receive identical input")
    m27_smoke=[receipts["p6_m27_smoke"],receipts["p9_m27_smoke"]]
    m27_review=[receipts["p6_m27_review"],receipts["p9_m27_review"]]
    for entry in m27_smoke+m27_review:
        if entry["status"]!="COMPLETED" or entry["model_completed"] is not True:
            raise ValueError("Required M2.7 review is not a completed model execution")
        if entry["tool_calls"]!=0 or entry["model_visible_tools"]!=0:
            raise ValueError("Model tools were not fully disabled in experiment")
        if entry["actual_model"]!="MiniMax-M2.7":
            raise ValueError("Effective model differs from requested profile")
    bounded_total=sum(x["total_tokens"] for x in m27_review)
    summary={
      "schema":"cxpan.egm_b3r3_results/1",
      "date":"2026-10-27",
      "source_revision":"e825140caa2929ff6d338afb3c77ea657c3a627b",
      "experiments":receipts,
      "smoke_m27_medium":{
          "completed":len(m27_smoke),
          "attempted":len(m27_smoke),
          "total_elapsed_seconds":round(sum(x["elapsed_seconds"] for x in m27_smoke),3),
          "total_tokens":sum(x["total_tokens"] for x in m27_smoke),
          "claim":"Two independent domain snapshots; one completed smoke run each; not a statistical uptime estimate."
      },
      "bounded_review_m27_medium":{
          "completed":len(m27_review),
          "attempted":len(m27_review),
          "total_elapsed_seconds":round(sum(x["elapsed_seconds"] for x in m27_review),3),
          "total_tokens":bounded_total,
          "total_findings":sum(x["findings_count"] for x in m27_review),
          "format":"strict parseable JSON; <=2 findings per run"
      },
      "paired_same_prompt_control":{
          "source":"p6-evidence-integrity",
          "input_identical":True,
          "M27_medium_status":p6["status"],
          "M27_medium_seconds":p6["elapsed_seconds"],
          "M31_flash_adaptive_status":flash["status"],
          "M31_flash_adaptive_seconds":flash["elapsed_seconds"],
          "confounding":"Different supported thinking levels and models; one run each, not a causal model-only comparison."
      },
      "invalid_profile":{
         "profile":"minimax/MiniMax-M2.7 + adaptive",
         "status":receipts["p6_m27_invalid"]["status"],
         "preflight_rejects_without_model_completion":True,
         "known_supported_m27_setting":"medium",
      },
      "independent_offline_checks":{
          "evidence_capsule":invariant["evidence_capsule"],
          "safe_quota":invariant["safe_quota"],
      },
      "billing_cost_usd":None,
      "production_config_changed":False,
      "proposed_routing":"Opt-in model-profile guard for bounded, read-only reviews only; no production default change.",
      "limitations":[
          "No repeated trials or provider SLA; cannot infer stable reliability probability.",
          "Completing a model request does not validate every model finding.",
          "P6 capsule mismatch is a real producer/verifier invariant gap on synthetic allowed bytes, not proof existing static public docs are broken.",
          "P9 quota is an observable accounting behavior; whether failed unique attempts should count is a product/security policy decision.",
          "Real cost from provider billing unavailable.",
          "Not an official EGM five-stage benchmark or installation."
      ]
    }
    return summary


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--receipts",required=True)
    p.add_argument("--invariants",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    inv=json.loads(Path(args.invariants).read_text(encoding="utf-8"))
    result=summarize(Path(args.receipts),inv)
    dest=Path(args.out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "m27_smoke":result["smoke_m27_medium"]["completed"],
        "m27_review":result["bounded_review_m27_medium"]["completed"],
        "original_flash_status":result["paired_same_prompt_control"]["M31_flash_adaptive_status"],
        "p6_confirmed_capsule_mismatch":result["independent_offline_checks"]["evidence_capsule"]["verification_rejected"],
        "p9_quota_retry_allowed":result["independent_offline_checks"]["safe_quota"]["same_key_retried_without_second_slot"]
    },ensure_ascii=False))
