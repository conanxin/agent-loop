#!/usr/bin/env python3
"""Reproduce two narrow source-backed observations without touching production.

1. Existing evidence producer may serialize beyond the verifier's raw-JSON cap.
2. Safe task quota is reserved before the upstream submission succeeds; the
   same idempotency key can still be retried without consuming a second slot.

Only synthetic data and TemporaryDirectory SQLite. No live Hub/MCP request.
"""
from pathlib import Path
import argparse
import json
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"bridge"))
import evidence
import mcp_gateway


def check_capsule():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        (root/"docs").mkdir()
        file=root/"docs/SPEC.md"
        file.write_bytes(b"\x01"*10000)
        encoded=evidence.capture(root,"docs/SPEC.md")
        rejected=False
        rejection=None
        try:
            evidence.verify(encoded)
        except ValueError as err:
            rejected=True
            rejection=str(err)
        return {
            "input_is_valid_under_current_source_checks":True,
            "original_bytes":len(file.read_bytes()),
            "json_capsule_bytes":len(encoded.encode("utf-8")),
            "max_source_bytes":evidence.MAX_BYTES,
            "max_line_count":evidence.MAX_LINES,
            "verification_rejected":rejected,
            "verification_error":rejection,
            "analysis":"Capture source acceptance does not imply verifier acceptance for high JSON-escaping content.",
            "scope":"Synthetic valid UTF-8 fixture; not the three present static public docs or evidence of unauthenticated source modification."
        }


def check_quota():
    with tempfile.TemporaryDirectory() as d:
        old=mcp_gateway.QUOTA_DB
        mcp_gateway.QUOTA_DB=Path(d)/"quota.sqlite3"
        try:
            key="egm-b3r3-synthetic-key"
            actor="synthetic-client"
            mcp_gateway.quota_slot(actor,key)
            # Represents the subsequent upstream task submission failing.
            failed_upstream=True
            conn=sqlite3.connect(mcp_gateway.QUOTA_DB)
            rows_after_failure=conn.execute("SELECT COUNT(*) FROM quotas").fetchone()[0]
            # Exactly the same key remains retryable as the quota function returns.
            mcp_gateway.quota_slot(actor,key)
            rows_after_same_key_retry=conn.execute("SELECT COUNT(*) FROM quotas").fetchone()[0]
            mcp_gateway.quota_slot(actor,key+"2")
            distinct_rows=conn.execute("SELECT COUNT(*) FROM quotas").fetchone()[0]
            conn.close()
        finally:
            mcp_gateway.QUOTA_DB=old
        return {
            "same_client":actor,
            "simulated_upstream_failure":failed_upstream,
            "reserved_rows_after_failure":rows_after_failure,
            "reserved_rows_after_same_key_reuse":rows_after_same_key_retry,
            "reserved_rows_after_second_unique_key":distinct_rows,
            "same_key_retried_without_second_slot":rows_after_same_key_retry==rows_after_failure,
            "analysis":"Quota slots count unique attempted keys on UTC day; retrying the same key remains possible. Whether failed attempts should consume a slot is a policy decision, not automatically a vulnerability.",
            "production_db_untouched":True
        }


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result={"schema":"cxpan.egm_b3r3_invariants/1",
            "evidence_capsule":check_capsule(),"safe_quota":check_quota(),
            "no_production_file_or_database_mutation":True}
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "capsule_rejected":result["evidence_capsule"]["verification_rejected"],
        "capsule_serialized_bytes":result["evidence_capsule"]["json_capsule_bytes"],
        "quota_failed_attempt_consumed_slot":result["safe_quota"]["reserved_rows_after_failure"]==1,
        "same_key_retry_allowed":result["safe_quota"]["same_key_retried_without_second_slot"]
    },ensure_ascii=False),flush=True)
