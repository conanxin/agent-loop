#!/usr/bin/env python3
"""Operator-initiated two-reviewer primary-source experiment (P6).

Capture a fixed allowlisted file once, wait for its immutable result, submit
both reviewers with the SAME parent and SHA256, then verify their receipts.
No automatic retries of failed/possibly running expensive model tasks.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from client import request_json
from evidence import SOURCES, verify, check_line_citations

WORKFLOW_RE = re.compile(r"^[A-Za-z0-9_-]{8,60}$")
STATE_DIR = Path.home() / ".local/state/cx-pan/workflows"
REVIEWERS = (
    ("hermes_primary", "hermes.evidence.local"),
    ("openclaw_primary", "openclaw.evidence.cloud"),
)


def wait_receipt(task_id, seconds=170):
    limit = time.monotonic() + seconds
    while True:
        result = request_json("GET", f"/v1/tasks/{task_id}/result")
        status = result["task"]["status"]
        if status in ("COMPLETED", "FAILED"):
            return result
        if time.monotonic() > limit:
            raise TimeoutError(
                f"task {task_id} in {status}; inspect manually, DO NOT re-run blindly"
            )
        time.sleep(4)


def submit(idempotency_key, target, capability, goal,
           repo_id="none", parent_id=None, digest=None):
    data = {
        "idempotency_key": idempotency_key,
        "requester": "cxpan.primary_source",
        "project_id": "CX-PAN",
        "target": target,
        "capability": capability,
        "goal": goal,
        "repo_id": repo_id,
    }
    if parent_id:
        data.update({"parent_task_id": parent_id, "source_sha256": digest})
    result = request_json("POST", "/v1/tasks", data)
    print(f"SUBMITTED {target} id={result['task']['task_id']} "
          f"duplicate={result['duplicate']}", flush=True)
    return result["task"]["task_id"]


def run(flow_id, source_path, claim, max_wait):
    if not WORKFLOW_RE.fullmatch(flow_id):
        raise ValueError("workflow_id must be 8–60 ASCII letters/numbers/hyphen")
    if source_path not in SOURCES:
        raise ValueError("source is outside the approved allowlist")
    if not isinstance(claim, str) or not (10 <= len(claim) <= 500):
        raise ValueError("claim must be 10–500 characters")
    evidence_task_id = submit(
        f"p6-{flow_id}-capture", "repo.evidence.local", "source.capture",
        source_path, repo_id="agent-loop"
    )
    original = wait_receipt(evidence_task_id, max_wait)
    if original["task"]["status"] != "COMPLETED":
        raise RuntimeError("source capture failed, no reviewer task submitted")
    text = original.get("result_text") or ""
    outer_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source = verify(text, outer_digest)
    if source["path"] != source_path:
        raise ValueError("captured source does not match requested file")
    print(f"SOURCE_VERIFIED path={source_path} original_sha256={source['sha256']} "
          f"bytes={source['size_bytes']} result_sha256={outer_digest}", flush=True)
    children = []
    for name, target in REVIEWERS:
        task_id = submit(
            f"p6-{flow_id}-{name}", target, "source.verify", claim,
            parent_id=evidence_task_id, digest=outer_digest
        )
        children.append((name, task_id))
    receipt = {
        "schema": "cxpan.primary_review/1",
        "workflow_id": flow_id,
        "source_task_id": evidence_task_id,
        "source_path": source_path,
        "source_sha256": source["sha256"],
        "source_result_sha256": outer_digest,
        "source_size_bytes": source["size_bytes"],
        "claim": claim,
        "reviewers": [],
    }
    overall = True
    for name, task_id in children:
        result = wait_receipt(task_id, max_wait)
        status = result["task"]["status"]
        link = result.get("provenance") or {}
        if link.get("parent_task_id") != evidence_task_id or (
            link.get("source_sha256") != outer_digest
        ):
            raise ValueError("reviewer task has mismatched source provenance")
        raw = result.get("result_text") or ""
        model = {}
        if status == "COMPLETED":
            try:
                model = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{name} returned malformed review JSON") from exc
            meta = model.get("source") or {}
            if (meta.get("sha256") != source["sha256"] or
                meta.get("path") != source_path or
                meta.get("size_bytes") != source["size_bytes"] or
                model.get("source_verified_before_model") is not True):
                raise ValueError(f"{name} did not verify the original source")
            citations = check_line_citations(model.get("model_response"), source)
        else:
            overall = False
        entry = {
            "reviewer": name, "task_id": task_id,
            "status": status, "run_id": result["task"].get("run_id"),
            "model_response_chars": len(model.get("model_response") or ""),
            "evidence_verified": status == "COMPLETED",
            "explicit_citations_in_range": len(citations) if status == "COMPLETED" else 0,
            "error": (result.get("error_text") or "")[:500],
        }
        receipt["reviewers"].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    receipt["status"] = "COMPLETED" if overall else "FAILED"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / (f"p6-{flow_id}.json")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    tmp.replace(path)
    print(f"RESULT {receipt['status']} receipt={path}", flush=True)
    return 0 if overall else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--source", required=True, choices=sorted(SOURCES))
    parser.add_argument("--claim", required=True)
    parser.add_argument("--stage-timeout", type=int, default=175)
    args = parser.parse_args()
    if not 15 <= args.stage_timeout <= 300:
        parser.error("stage-timeout must be 15..300")
    try:
        return run(args.workflow_id, args.source, args.claim, args.stage_timeout)
    except (RuntimeError, ValueError, KeyError, TimeoutError, OSError) as exc:
        print(f"P6 evidence workflow stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
