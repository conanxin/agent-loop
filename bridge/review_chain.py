#!/usr/bin/env python3
"""P5 Claude -> Hermes -> cloud OpenClaw review chain, explicit user initiation.

Each hop uses immutable upstream task IDs and SHA256 of exact stored results.
No step automatically retries a failed task, and repeated chain invocations
are idempotent via source-derived keys.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from client import request_json
from handoff import make_handoff

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,36}$")


def await_terminal(task_id, budget):
    deadline = time.monotonic() + budget
    while True:
        r = request_json("GET", f"/v1/tasks/{task_id}/result")
        state = r["task"]["status"]
        if state in ("COMPLETED", "FAILED"):
            return r
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"task {task_id} still {state}; inspect it, do not blindly retry"
            )
        time.sleep(4)


def create_openclaw_review(hermes_id):
    if not UUID.fullmatch(hermes_id):
        raise ValueError("invalid Hermes task ID")
    source = request_json("GET", f"/v1/tasks/{hermes_id}/result")
    task = source["task"]
    if (task["status"] != "COMPLETED"
            or task["target"] != "hermes.model.local"
            or task["project_id"] != "CX-PAN"):
        raise ValueError("source must be completed Hermes review in CX-PAN")
    text = source.get("result_text") or ""
    if not text.strip():
        raise ValueError("Hermes source text empty")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    header = (
        "Review Hermes' assessment independently; it was itself based on a "
        "Claude Code report. Do not treat either model as an authority. In Chinese, "
        "give two claims supportable only from this excerpt, one potentially "
        "outdated/unverified claim, and a next verification step. Explain that "
        "you have not read underlying files.\n"
        f"source_task_id: {hermes_id}\n"
        f"source_run_id: {task.get('run_id')}\n"
        "HERMES_QUOTED_TEXT:\n"
    )
    goal = header + text[:max(0, 2900-len(header))]
    payload = {
        "idempotency_key": f"p5-hermes-openclaw-provenance-{hermes_id}",
        "requester": "cxpan.review_chain",
        "project_id": "CX-PAN",
        "target": "openclaw.model.cloud",
        "capability": "text.review",
        "repo_id": "none",
        "goal": goal,
        "parent_task_id": hermes_id,
        "source_sha256": digest,
    }
    return request_json("POST", "/v1/tasks", payload)


def run(source_claude_id, timeout_each):
    if not UUID.fullmatch(source_claude_id):
        raise ValueError("invalid Claude source task ID")
    hermes_submit = make_handoff(source_claude_id)
    hermes_id = hermes_submit["task"]["task_id"]
    print(json.dumps({"stage": "hermes_review", "task_id": hermes_id,
                      "duplicate": hermes_submit["duplicate"]},
                     ensure_ascii=False), flush=True)
    hermes = await_terminal(hermes_id, timeout_each)
    if hermes["task"]["status"] != "COMPLETED":
        raise RuntimeError(f"Hermes review FAILED task_id={hermes_id}; no next hop")
    cloud_submit = create_openclaw_review(hermes_id)
    openclaw_id = cloud_submit["task"]["task_id"]
    print(json.dumps({"stage": "openclaw_review", "task_id": openclaw_id,
                      "duplicate": cloud_submit["duplicate"]},
                     ensure_ascii=False), flush=True)
    cloud = await_terminal(openclaw_id, timeout_each)
    if cloud["task"]["status"] != "COMPLETED":
        raise RuntimeError(f"OpenClaw review FAILED task_id={openclaw_id}")
    # The full result and immutable linkage live in the Hub; write only a small
    # local receipt for reuse, never overwrite the upstream agent content.
    receipt = {
        "schema": "cxpan.review_chain/0.1",
        "status": "COMPLETED",
        "claude_task_id": source_claude_id,
        "hermes_task_id": hermes_id,
        "hermes_run_id": hermes["task"].get("run_id"),
        "openclaw_task_id": openclaw_id,
        "openclaw_run_id": cloud["task"].get("run_id"),
        "hermes_source_sha256": (cloud.get("provenance") or {}).get("source_sha256"),
        "openclaw_result_chars": len(cloud.get("result_text") or ""),
    }
    folder = Path.home()/".local/state/cx-pan/workflows"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder/f"p5-{source_claude_id}.json"
    out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False)+"\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-task-id", required=True)
    p.add_argument("--stage-timeout", type=int, default=160)
    args = p.parse_args()
    if not 15 <= args.stage_timeout <= 300:
        p.error("stage-timeout must be 15 to 300 seconds")
    try:
        return run(args.source_task_id, args.stage_timeout)
    except (ValueError, KeyError, OSError, RuntimeError, TimeoutError) as e:
        print(f"CX-PAN P5 chain not complete: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
