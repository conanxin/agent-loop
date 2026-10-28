#!/usr/bin/env python3
"""CX-PAN P10 private Pi text-only worker. Not a public MCP endpoint.

Claims only pi.text.cloud tasks from the token-authenticated local Hub.
The fixed dispatcher invokes Windows Pi with --no-tools/--no-mcp and
reads the model key only on xinhailin. No general Windows shell is offered.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from client import request_json

TARGET = "pi.text.cloud"
CAPABILITY = "pi.text"
WORKER_ID = "tencent-xinhailin-pi-text"
DISPATCHER = Path("/home/ubuntu/cxpan-xinhailin/dispatcher.py")
QUOTA = Path.home() / ".local/share/cx-pan/pi_text_daily.sqlite3"
MAX_DAILY_TASKS = 6
MAX_PROMPT_CHARS = 1200
MAX_RESPONSE_CHARS = 15000


def quota_reserve(task_id: str) -> None:
    """Persist bounded new-model runs across worker restarts."""
    QUOTA.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = sqlite3.connect(QUOTA, timeout=6)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS runs(task_id TEXT PRIMARY KEY, utc_day TEXT NOT NULL)")
        today = datetime.now(timezone.utc).date().isoformat()
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT 1 FROM runs WHERE task_id=?", (task_id,)).fetchone()
        if not prior:
            count = conn.execute("SELECT count(*) FROM runs WHERE utc_day=?", (today,)).fetchone()[0]
            if count >= MAX_DAILY_TASKS:
                raise RuntimeError("daily Pi text model allowance reached")
            conn.execute("INSERT INTO runs(task_id,utc_day) VALUES(?,?)", (task_id, today))
        conn.commit()
    finally:
        conn.close()


def run_model(task):
    assert task["target"] == TARGET and task["capability"] == CAPABILITY
    if task["repo_id"] != "none" or task["project_id"] != "CX-PAN":
        raise ValueError("Pi private task scope invalid")
    if task["requester"] not in ("cxpan.internal.pi", "mcp.chatgpt.pi"):
        raise ValueError("Pi task requester not approved")
    goal = task["goal"]
    if not isinstance(goal, str) or not (4 <= len(goal) <= MAX_PROMPT_CHARS):
        raise ValueError("Pi prompt length outside approved text-only bounds")
    if not DISPATCHER.is_file():
        raise RuntimeError("Pi cloud dispatcher unavailable")
    if os.environ.get("P10_PI_WORKER_DRYRUN") == "1":
        return json.dumps({"dry_run": True, "model_invoked": False,
                           "device": "xinhailin", "answer": "PI_WORKER_DRY_RUN_OK"},
                          ensure_ascii=False), "pi:dryrun:" + str(uuid.uuid4())
    quota_reserve(task["task_id"])
    outcome = subprocess.run(
        [sys.executable, str(DISPATCHER)], input=goal.encode("utf-8"),
        capture_output=True, timeout=165, cwd=str(DISPATCHER.parent),
        check=False,
    )
    if outcome.returncode:
        raise RuntimeError("Pi dispatcher failed with exit code " + str(outcome.returncode))
    try:
        receipt = json.loads(outcome.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise RuntimeError("Pi dispatcher returned an invalid receipt") from e
    if (receipt.get("status") != "completed" or receipt.get("exit_code") != 0
        or receipt.get("device") != "xinhailin" or
        receipt.get("provider") != "minimax-cn" or
        receipt.get("model") != "MiniMax-M2.7"):
        raise RuntimeError("Pi dispatcher did not report a valid completed model run")
    answer = receipt.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Pi model response missing")
    result = {
        "device": "xinhailin", "agent": "Pi", "provider": "minimax-cn",
        "model": "MiniMax-M2.7", "mode": "text-only/no-tools/no-session",
        "answer": answer[:MAX_RESPONSE_CHARS],
        "elapsed_seconds": receipt.get("elapsed_seconds")
    }
    return json.dumps(result, ensure_ascii=False), "pi:xinhailin:" + str(uuid.uuid4())


def heartbeat(task, stop):
    payload = {key: task[key] for key in ("task_id", "attempt_id", "worker_id")}
    while not stop.wait(15):
        try:
            request_json("POST", "/v1/workers/heartbeat", payload)
        except Exception:
            pass


def run_once():
    data = request_json("POST", "/v1/workers/claim", {
        "worker_id": WORKER_ID, "targets": [TARGET],
    })
    task = data.get("task")
    if task is None:
        print("PI_TEXT_QUEUE_EMPTY", flush=True)
        return False
    task["worker_id"] = WORKER_ID
    print("PI_TEXT_CLAIMED", task["task_id"], flush=True)
    stop = threading.Event()
    pulse = threading.Thread(target=heartbeat, args=(task, stop), daemon=True)
    pulse.start()
    try:
        try:
            result, run_id = run_model(task)
            state, error = "COMPLETED", ""
        except Exception as exc:
            result, run_id, state = "", "pi:failed:" + str(uuid.uuid4()), "FAILED"
            error = (type(exc).__name__ + ": " + str(exc))[:700]
    finally:
        stop.set()
        pulse.join(timeout=2)
    request_json("POST", "/v1/workers/report", {
        "task_id": task["task_id"], "attempt_id": task["attempt_id"],
        "worker_id": WORKER_ID, "status": state, "run_id": run_id,
        "result_text": result, "error_text": error,
    })
    print("PI_TEXT_FINISHED", task["task_id"], state, flush=True)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=20)
    args = ap.parse_args()
    if args.once:
        run_once()
        return
    while True:
        try:
            run_once()
        except Exception as exc:
            print("PI_WORKER_ERROR " + type(exc).__name__, file=sys.stderr, flush=True)
        time.sleep(max(8, args.interval))


if __name__ == "__main__":
    main()
