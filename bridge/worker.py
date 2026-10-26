#!/usr/bin/env python3
"""Local outbound CX-PAN worker. No inbound port; no direct Gateway calls.

Echo tasks are deterministic. Claude Code tasks are limited to read-only,
noninteractive repository inspection with read/search tools only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from client import request_json

WORKER_ID = os.getenv("CX_PAN_WORKER_ID", "wsl2-readonly-worker")
REPO = Path.home() / "workspace/projects/agent-loop"
CLAUDE_EXE = os.getenv("CX_PAN_CLAUDE_BIN", str(Path.home() / ".local/bin/claude"))
CLAUDE_MODEL = os.getenv("CX_PAN_CLAUDE_MODEL", "haiku")


def execute(task):
    target = task["target"]
    if target == "echo.local":
        return f"ECHO_OK: {task['goal']}", "echo:" + str(uuid.uuid4())
    if target != "claude.code.local" or task["repo_id"] != "agent-loop":
        raise ValueError("unsupported worker task")
    if not REPO.joinpath(".git").is_dir():
        raise FileNotFoundError("approved agent-loop repository missing")
    if not Path(CLAUDE_EXE).is_file() and not shutil.which(CLAUDE_EXE):
        raise FileNotFoundError("claude code binary missing")
    prompt = (
        "This is a READ-ONLY assessment of the approved agent-loop repository. "
        "Do not edit any files, run shell commands, install software or call "
        "external services. Only inspect files in the current repository. "
        "Respond in Chinese with confirmed findings, source file paths, "
        "uncertainties and recommended next steps. User request: "
        + task["goal"]
    )
    command = [
        CLAUDE_EXE, "-p", prompt,
        "--output-format", "json",
        "--no-session-persistence",
        "--permission-mode", "dontAsk",
        "--allowedTools", "Read,Glob,Grep",
        "--disallowedTools", "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch",
        "--model", CLAUDE_MODEL,
        "--max-turns", "4",
        "--max-budget-usd", "0.20",
    ]
    proc = subprocess.run(
        command, cwd=REPO, capture_output=True, text=True, timeout=150,
        env={**os.environ, "CI": "1"}, stdin=subprocess.DEVNULL
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Claude Code exited {proc.returncode}: " +
                           proc.stderr[-1000:])
    try:
        obj = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Claude Code did not return parseable JSON") from exc
    if obj.get("is_error"):
        raise RuntimeError("Claude Code returned an error result")
    result = obj.get("result")
    if not isinstance(result, str) or not result.strip():
        raise RuntimeError("Claude Code returned empty result")
    return result[:45000], obj.get("session_id") or "claude:" + str(uuid.uuid4())


def run_once(targets):
    response = request_json("POST", "/v1/workers/claim", {
        "worker_id": WORKER_ID,
        "targets": targets,
    })
    task = response.get("task")
    if task is None:
        print("NO_QUEUED_TASK", flush=True)
        return False
    task_id = task["task_id"]
    print(f"CLAIMED task_id={task_id} target={task['target']}", flush=True)
    try:
        result, run_id = execute(task)
        status, error = "COMPLETED", ""
    except Exception as exc:
        result, run_id = "", "failed:" + str(uuid.uuid4())
        status, error = "FAILED", f"{type(exc).__name__}: {str(exc)}"[:4000]
    request_json("POST", "/v1/workers/report", {
        "task_id": task_id,
        "attempt_id": task["attempt_id"],
        "worker_id": WORKER_ID,
        "status": status,
        "run_id": str(run_id)[:128],
        "result_text": result,
        "error_text": error,
    })
    print(f"FINISHED task_id={task_id} status={status}", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--target", choices=("echo.local", "claude.code.local",
                                             "both"), default="both")
    args = parser.parse_args()
    targets = ["echo.local", "claude.code.local"] if args.target == "both" else [args.target]
    if args.once:
        run_once(targets)
        return
    while True:
        try:
            run_once(targets)
        except Exception as exc:
            print(f"WORKER_CONNECTIVITY_ERROR {type(exc).__name__}", file=sys.stderr,
                  flush=True)
        time.sleep(max(args.interval, 5))


if __name__ == "__main__":
    main()
