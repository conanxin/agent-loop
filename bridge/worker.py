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
import threading
import uuid
from pathlib import Path
from client import request_json

WORKER_ID = os.getenv("CX_PAN_WORKER_ID", "wsl2-readonly-worker")
REPO = Path.home() / "workspace/projects/agent-loop"
CLAUDE_EXE = os.getenv("CX_PAN_CLAUDE_BIN", str(Path.home() / ".local/bin/claude"))
CLAUDE_MODEL = os.getenv("CX_PAN_CLAUDE_MODEL", "haiku")
# A $0.20 CLI cost estimate can terminate a short read-only model task.
# Preserve an explicit per-run ceiling, configurable for personal use.
CLAUDE_MAX_BUDGET_USD = os.getenv("CX_PAN_CLAUDE_MAX_BUDGET_USD", "0.75")
HEALTH_TARGETS = {
    "hermes.health.local": ("hermes-gateway.service", "hermes"),
    "openclaw.health.local": ("openclaw-gateway.service", "openclaw"),
}
AVAILABLE_TARGETS = (
    "echo.local", "claude.code.local",
    "hermes.health.local", "openclaw.health.local", "repo.validate.local"
)


def read_gateway_health(target):
    service, binary = HEALTH_TARGETS[target]
    # Read-only service status and version. No model turn, shell, or Gateway API.
    systemd = subprocess.run(
        ["systemctl", "--user", "is-active", service],
        capture_output=True, text=True, timeout=8
    )
    exe = str(Path.home() / ".local/bin" / binary)
    node_dir = str(Path.home() / ".local/share/fnm/node-versions/v24.20.0/installation/bin")
    env = {**os.environ, "PATH": node_dir + os.pathsep + os.environ.get("PATH", "")}
    version = subprocess.run(
        [exe, "--version"], capture_output=True, text=True,
        timeout=12, env=env, stdin=subprocess.DEVNULL
    )
    if version.returncode != 0:
        raise RuntimeError(binary + " version command failed")
    state = systemd.stdout.strip() or "unknown"
    first = next((line.strip() for line in version.stdout.splitlines() if line.strip()), "")
    return json.dumps({
        "agent": binary, "service": service,
        "gateway_state": state, "cli_version": first,
        "mode": "read_only_health_check", "model_invoked": False
    }, ensure_ascii=False), "health:" + str(uuid.uuid4())


def heartbeat_until_stopped(stop, task):
    payload = {
        "task_id": task["task_id"], "attempt_id": task["attempt_id"],
        "worker_id": WORKER_ID
    }
    while not stop.wait(20):
        try:
            request_json("POST", "/v1/workers/heartbeat", payload)
        except Exception:
            # Report will still be attempted; stale status becomes visible in Hub.
            pass


def validate_repo():
    """Fixed, non-user-controlled verification command in one approved repo."""
    if not REPO.joinpath(".git").is_dir():
        raise RuntimeError("approved repository missing")
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"]
    proc = subprocess.run(
        command, cwd=REPO, capture_output=True, text=True,
        timeout=55, stdin=subprocess.DEVNULL
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError("repo validation failed, exit_code=" + str(proc.returncode))
    # Only the test count / final status are needed in the handoff.
    import re
    m = re.search(r"Ran (\d+) tests? in", output)
    if not m or "OK" not in output[-300:]:
        raise RuntimeError("repo validation returned no canonical unittest receipt")
    return json.dumps({
        "repo_id": "agent-loop", "runner": "unittest discover",
        "tests_run": int(m.group(1)), "status": "PASS",
        "model_invoked": False
    }), "verify:" + str(uuid.uuid4())


def execute(task):
    target = task["target"]
    if target == "echo.local":
        return f"ECHO_OK: {task['goal']}", "echo:" + str(uuid.uuid4())
    if target in HEALTH_TARGETS and task["capability"] == "gateway.health" and task["repo_id"] == "none":
        return read_gateway_health(target)
    if target == "repo.validate.local" and task["capability"] == "repo.validate" and task["repo_id"] == "agent-loop":
        return validate_repo()
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
        "--max-budget-usd", CLAUDE_MAX_BUDGET_USD,
    ]
    proc = subprocess.run(
        command, cwd=REPO, capture_output=True, text=True, timeout=150,
        env={**os.environ, "CI": "1"}, stdin=subprocess.DEVNULL
    )
    if proc.returncode != 0:
        # The CLI often reports provider failures in JSON stdout, not stderr.
        # Keep only a short machine status identifier, never raw session text.
        try:
            failure = json.loads(proc.stdout)
            subtype = failure.get("subtype") or failure.get("error_type") or "unknown"
            if not isinstance(subtype, str) or not (
                1 <= len(subtype) <= 80 and
                all(c.isascii() and (c.isalnum() or c in "-_.") for c in subtype)
            ):
                subtype = "unclassified"
        except (json.JSONDecodeError, TypeError, AttributeError):
            subtype = "no_json_response"
        raise RuntimeError(
            f"Claude Code exited {proc.returncode}; result_subtype={subtype}; "
            f"stdout_bytes={len(proc.stdout or '')}; stderr_bytes={len(proc.stderr or '')}"
        )
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
    stop = threading.Event()
    thread = threading.Thread(
        target=heartbeat_until_stopped, args=(stop, task),
        daemon=True, name="cxpan-heartbeat"
    )
    thread.start()
    try:
        try:
            result, run_id = execute(task)
            status, error = "COMPLETED", ""
        except Exception as exc:
            result, run_id = "", "failed:" + str(uuid.uuid4())
            status, error = "FAILED", f"{type(exc).__name__}: {str(exc)}"[:4000]
    finally:
        stop.set()
        thread.join(timeout=2)
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
    parser.add_argument("--target", choices=(*AVAILABLE_TARGETS, "both"), default="both")
    args = parser.parse_args()
    targets = list(AVAILABLE_TARGETS) if args.target == "both" else [args.target]
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
