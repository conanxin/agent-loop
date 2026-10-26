#!/usr/bin/env python3
"""CX-PAN P3 resumable, sequential readiness workflow.

This is an operator-run orchestrator, not a background server. A stable workflow
ID yields stable idempotency keys, so restarting it will inspect already-completed
tasks instead of starting duplicates. It never automatically retries failed tasks.
"""
import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from client import request_json

STAGES = (
    ("repository_validation", "repo.validate.local", "repo.validate", "agent-loop",
     "Run the fixed agent-loop unittest suite without modifying production tasks."),
    ("hermes_gateway", "hermes.health.local", "gateway.health", "none",
     "Read-only verify Hermes Gateway activity and installed CLI version."),
    ("openclaw_gateway", "openclaw.health.local", "gateway.health", "none",
     "Read-only verify OpenClaw Gateway activity and installed CLI version."),
)
CLAUDE = (
    "claude_readonly_research", "claude.code.local", "repo.inspect", "agent-loop",
    "Read README.md and docs/CX_PAN_INTEGRATION.md in the agent-loop repository. "
    "Summarize the original goal, cite files read, and identify one next improvement. "
    "Do not write code or run shell commands."
)
STATE_DIR = Path.home() / ".local/state/cx-pan/workflows"
WORKFLOW_ID = re.compile(r"^[a-zA-Z0-9_-]{8,60}$")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    os.replace(temp, path)


def run(args):
    flow_id = args.workflow_id or "p3-" + uuid.uuid4().hex[:20]
    if not WORKFLOW_ID.fullmatch(flow_id):
        raise ValueError("workflow ID must be 8–60 ASCII letters, numbers, - or _")
    stages = ((CLAUDE,) if args.with_claude else ()) + STAGES
    local = STATE_DIR / (flow_id + ".json")
    if local.exists():
        previous = json.loads(local.read_text(encoding="utf-8"))
        if previous.get("with_claude") != args.with_claude:
            raise ValueError("workflow ID already used with different stage selection")
    data = {
        "schema": "cxpan.workflow/0.1",
        "workflow_id": flow_id,
        "with_claude": args.with_claude,
        "mode": "operator_initiated",
        "status": "RUNNING",
        "created_at": now(),
        "updated_at": now(),
        "stages": []
    }
    if local.exists():
        data["created_at"] = previous.get("created_at") or now()
    save(data, local)

    previous_task_id = None
    for name, target, capability, repo_id, goal in stages:
        scoped_goal = goal + (f" Previous accepted task: {previous_task_id}." if previous_task_id else "")
        payload = {
            "idempotency_key": f"p3-{flow_id}-{name}",
            "requester": "cxpan.workflow",
            "project_id": "CX-PAN",
            "target": target,
            "capability": capability,
            "repo_id": repo_id,
            "goal": scoped_goal
        }
        posted = request_json("POST", "/v1/tasks", payload)
        task_id = posted["task"]["task_id"]
        print(f"{name}: id={task_id} duplicate={posted['duplicate']}", flush=True)
        deadline = time.monotonic() + args.stage_timeout
        while True:
            receipt = request_json("GET", f"/v1/tasks/{task_id}/result")
            status = receipt["task"]["status"]
            if status in ("COMPLETED", "FAILED"):
                break
            if time.monotonic() >= deadline:
                data["status"] = "NEEDS_REVIEW"
                data["updated_at"] = now()
                data["stages"].append({
                    "name": name, "task_id": task_id, "state": status,
                    "health": receipt["task"].get("execution_health"),
                    "note": "Timeout while waiting; do not automatically resubmit"
                })
                save(data, local)
                print(f"NEEDS_REVIEW workflow_id={flow_id} stage={name}", flush=True)
                return 2
            time.sleep(args.poll)
        result = receipt.get("result_text") or ""
        entry = {
            "name": name,
            "task_id": task_id,
            "state": status,
            "run_id": receipt["task"].get("run_id"),
            "health": receipt["task"].get("execution_health"),
            "result_preview": result[:2000],
            "result_length": len(result),
            "error": (receipt.get("error_text") or "")[:600],
        }
        data["stages"].append(entry)
        data["updated_at"] = now()
        save(data, local)
        print(f"{name}: {status}, run_id={entry['run_id']}", flush=True)
        if status != "COMPLETED":
            data["status"] = "FAILED"
            save(data, local)
            print(f"FAILED workflow_id={flow_id} stage={name} receipt={local}", flush=True)
            return 1
        previous_task_id = task_id

    data["status"] = "COMPLETED"
    data["updated_at"] = now()
    save(data, local)
    print(f"COMPLETED workflow_id={flow_id} stages={len(data['stages'])} receipt={local}",
          flush=True)
    return 0


def main():
    p = argparse.ArgumentParser(description="Sequential, idempotent CX-PAN P3 checks")
    p.add_argument("--workflow-id", help="Stable ID enables safe reinspection")
    p.add_argument("--with-claude", action="store_true",
                   help="Prepend a real Claude Code read-only repository analysis")
    p.add_argument("--stage-timeout", type=int, default=180)
    p.add_argument("--poll", type=int, default=4)
    args = p.parse_args()
    if not (10 <= args.stage_timeout <= 600) or not (1 <= args.poll <= 30):
        p.error("stage-timeout must be 10..600, poll 1..30")
    try:
        return run(args)
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        print(f"CX-PAN workflow error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
