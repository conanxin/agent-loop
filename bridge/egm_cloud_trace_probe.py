#!/usr/bin/env python3
"""One isolated OpenClaw agent exec with retained scratch state for B2 trace audit.

Unlike the regular headless invocation that deletes its temporary state, this
uses an operator-owned, empty --state-dir and stores the resulting transcript.
All data stays on the cloud host. No Gateway settings or production state touched.
"""
import argparse
import atexit
import secrets
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

HOME = Path.home()
BASE = HOME / ".local/state/cx-pan/egm"
CLI = HOME / ".npm-global/bin/openclaw"
PINNED = HOME / ".openclaw/cxpan-p5-readonly.json5"


def summarize_jsonl(p):
    result = {"relative_path": str(p), "lines": 0, "roles": {},
              "typed_events": {}, "tool_call_records": 0,
              "parse_errors": 0}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        result["lines"] += 1
        try:
            row = json.loads(line)
        except ValueError:
            result["parse_errors"] += 1
            continue
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type") or "unknown")
        result["typed_events"][kind] = result["typed_events"].get(kind, 0) + 1
        msg = row.get("message") if isinstance(row.get("message"), dict) else row
        role = msg.get("role")
        if role:
            result["roles"][str(role)] = result["roles"].get(str(role), 0) + 1
        blocks = msg.get("content") if isinstance(msg.get("content"), list) else []
        for block in blocks:
            if isinstance(block, dict) and str(block.get("type")) in (
                "toolCall", "toolResult", "tool_use", "tool_result"):
                result["tool_call_records"] += 1
    return result


def run(name, timeout, challenge_tool=False, disable_tool_search=False):
    if not re.fullmatch(r"egm-b2-[a-z0-9-]{8,60}", name):
        raise ValueError("invalid audit name")
    root = BASE / name
    receipt_file = root / "receipt.json"
    if receipt_file.exists():
        existing = json.loads(receipt_file.read_text(encoding="utf-8"))
        print("REUSED_EXISTING", existing["status"], str(receipt_file), flush=True)
        return
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("Incomplete previous experiment: inspect before rerunning")
    root.mkdir(parents=True, exist_ok=True)
    state = root / "state"
    state.mkdir()
    prompt_file = root / "prompt.txt"
    prompt_text = (
        "Controlled tool-policy test. If the tool_search interface is available, "
        "try exactly one tool_search query for 'egm-b2-synthetic-tool-lookup'. "
        "Do not read files, browse websites, run commands, or modify anything. "
        "Then summarize whether the tool call succeeded or was unavailable."
        if challenge_tool else
        "This is an internal tooling trace check, do not use tools or files. "
        "Reply with exactly EGM_B2_TRACE_OK."
    )
    prompt_file.write_text(prompt_text, encoding="utf-8")
    conf = PINNED.read_text(encoding="utf-8")
    if '"deny": ["*"]' not in conf or '"contextInjection": "never"' not in conf:
        raise RuntimeError("missing pinned read-only deny/context policy")
    config_for_run = PINNED
    if disable_tool_search:
        config_for_run = PINNED.parent / ("cxpan-egm-notoolsearch-" + secrets.token_hex(8) + ".json5")
        config_for_run.write_text(
            conf.replace('"deny": ["*"]', '"deny": ["*"], "toolSearch": false'),
            encoding="utf-8")
        atexit.register(lambda: config_for_run.unlink(missing_ok=True))
    command = [
        str(CLI), "agent", "exec", "--config", str(config_for_run),
        "--cwd", str(root), "--state-dir", str(state),
        "--model", "minimax/MiniMax-M3.1-Flash",
        "--code-mode", "direct", "--local-model-lean",
        "--thinking", "adaptive", "--timeout", str(timeout - 10),
        "--json", "--message-file", str(prompt_file)]
    started = time.monotonic()
    try:
        p = subprocess.run(command, cwd=root, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        print("TIMEOUT; retained state dir", str(state), flush=True)
        return
    elapsed = round(time.monotonic() - started, 3)
    (root / "exec-output.json").write_text(p.stdout or "", encoding="utf-8")
    (root / "exec-stderr.txt").write_text(p.stderr or "", encoding="utf-8")
    try:
        j = json.loads(p.stdout)
    except (ValueError, TypeError):
        j = {}
    found = []
    for path in state.rglob("*.jsonl"):
        if not path.is_file() or path.stat().st_size > 1500000:
            continue
        summary = summarize_jsonl(path)
        summary["relative_path"] = path.relative_to(root).as_posix()
        found.append(summary)
    other_paths = sorted(str(f.relative_to(root)) for f in state.rglob("*") if f.is_file())
    # Notion/Git only receive metadata; credential-bearing config contents are
    # deliberately NOT copied into the report.
    receipt = {
        "schema": "cxpan.egm_cloud_trace/0.1", "name": name,
        "challenge_tool_search": challenge_tool,
        "tool_search_explicitly_disabled": disable_tool_search,
        "status": "COMPLETED" if p.returncode == 0 and j.get("ok") is True
                  and j.get("status") == "ok" else "FAILED",
        "exit_code": p.returncode, "elapsed_s": elapsed,
        "session_id": j.get("sessionId"),
        "final_matches_expected": j.get("final") == "EGM_B2_TRACE_OK",
        "provider": j.get("provider"), "model": j.get("model"),
        "envelope_tool_summary_present": "toolSummary" in j,
        "envelope_tool_calls": ((j.get("toolSummary") or {}).get("calls")
                                if isinstance(j.get("toolSummary"), dict) else None),
        "trace_jsonl": found,
        "retained_state_file_paths": other_paths[:80],
        "retained_state_file_count": len(other_paths),
        "state_retained_in_experiment_only": True,
        "state_dir": str(state),
        "limits": [
            "JSONL record counting is not a complete accounting of every possible host bridge",
            "No production service or pinned config modifications",
            "One synthetic model call only, no claim about arbitrary prompts or plugin behavior"
        ]
    }
    receipt_file.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print(json.dumps({"verdict": receipt["status"], "exit_code": p.returncode,
                      "session_id": receipt["session_id"], "elapsed_s": elapsed,
                      "expected_answer": receipt["final_matches_expected"],
                      "jsonl_files": len(found), "state_files": len(other_paths),
                      "envelope_tool_calls": receipt["envelope_tool_calls"],
                      "jsonl_tool_records": sum(x["tool_call_records"] for x in found)},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import sys
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--timeout", type=int, default=115)
    p.add_argument("--challenge-tool", action="store_true")
    p.add_argument("--disable-tool-search", action="store_true")
    a = p.parse_args()
    run(a.name, a.timeout, a.challenge_tool, a.disable_tool_search)
