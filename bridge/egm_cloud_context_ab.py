#!/usr/bin/env python3
"""Cloud OpenClaw contextInjection always-vs-never probe, no service changes.

Runs two independent OpenClaw agent exec calls in a synthetic workspace.
Both configs deny all tools; only workspace contextInjection is varied.
The original production pinned config is NOT modified.
"""
import argparse
import atexit
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

HOME = Path.home()
CLI = HOME / ".npm-global/bin/openclaw"
PINNED = HOME / ".openclaw/cxpan-p5-readonly.json5"
BASE = HOME / ".local/state/cx-pan/egm"
LEXICON = ["birch", "cobalt", "fern", "lantern", "otter", "rainbow",
           "willow", "delta", "harbor", "maple", "canyon", "tulip",
           "copper", "starlight", "meadow", "compass"]


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def choose_words():
    return "-".join(secrets.SystemRandom().sample(LEXICON, 3))


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=True)
    ambient, source = choose_words(), choose_words()
    while source == ambient:
        source = choose_words()
    (folder / "AGENTS.md").write_text(
        "# EGM controlled workspace\n"
        "This is a synthetic non-secret instruction that tests workspace injection.\n"
        "When asked for AMBIENT_WORD, its value is exactly " + ambient + ".\n",
        encoding="utf-8")
    prompt_path = folder / "question.txt"
    prompt_path.write_text(
        "This is a read-only context-isolation test, do not call tools.\n"
        "Reply with exactly two lines; never guess an unknown workspace value.\n"
        "SOURCE_WORD=" + source + "\n"
        "AMBIENT_WORD=<the value in workspace rules if actually visible, otherwise NONE>\n",
        encoding="utf-8")
    old = PINNED.read_text(encoding="utf-8")
    if ('"deny": ["*"]' not in old or '"contextInjection": "never"' not in old
            or '"$include": "./openclaw.json"' not in old):
        raise RuntimeError("unrecognized pinned config; refuse to create probe configs")
    # OpenClaw deliberately forbids $include escaping the config directory.
    # Therefore place the temporary TEST config beside pinned openclaw.json;
    # never alter openclaw.json or the existing pinned production config.
    control = PINNED.parent / ("cxpan-egm-ab-" + secrets.token_hex(8) + ".json5")
    control.write_text(old.replace('"contextInjection": "never"',
                                   '"contextInjection": "always"'),
                       encoding="utf-8")
    atexit.register(lambda: control.unlink(missing_ok=True))
    return ambient, source, prompt_path, control


def run_one(label, config, folder, prompt_path, ambient, source, timeout):
    cmd = [str(CLI), "agent", "exec",
           "--config", str(config), "--cwd", str(folder),
           "--model", "minimax/MiniMax-M3.1-Flash",
           "--code-mode", "direct", "--local-model-lean",
           "--thinking", "adaptive", "--timeout", str(timeout - 10),
           "--json", "--message-file", str(prompt_path)]
    started = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        elapsed = round(time.monotonic() - started, 3)
        (folder / (label + ".stdout.json")).write_text(p.stdout or "",
                                                       encoding="utf-8")
        (folder / (label + ".stderr.txt")).write_text(p.stderr or "",
                                                       encoding="utf-8")
        try:
            j = json.loads(p.stdout)
        except (json.JSONDecodeError, TypeError):
            j = {}
        answer = j.get("final") or "\n".join(
            chunk.get("text", "") for chunk in j.get("payloads", [])
            if isinstance(chunk, dict)
        )
        tools = j.get("toolSummary")
        call_count = (tools.get("calls") if isinstance(tools, dict) else None)
        return {
            "label": label,
            "status": "COMPLETED" if p.returncode == 0 and j.get("ok") is True
                      and j.get("status") == "ok" else "FAILED",
            "exit_code": p.returncode, "elapsed_s": elapsed,
            "answer_chars": len(answer),
            "ambient_marker_seen_in_answer": ambient in answer,
            "explicit_source_marker_seen_in_answer": source in answer,
            "session_id": j.get("sessionId"),
            "tool_calls": call_count,
            "answer_sha256": sha(answer),
            "stderr_chars": len(p.stderr or ""),
        }
    except subprocess.TimeoutExpired:
        return {"label": label, "status": "TIMEOUT", "elapsed_s": timeout}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--timeout", type=int, default=125)
    args = parser.parse_args()
    if not (args.workflow_id.startswith("egm-b-")
            and args.workflow_id.replace("-", "").isalnum()):
        parser.error("invalid workflow ID")
    if not 60 <= args.timeout <= 200:
        parser.error("timeout must be 60..200s")
    folder = BASE / args.workflow_id
    receipt_path = folder / "receipt.json"
    if receipt_path.exists():
        j = json.loads(receipt_path.read_text())
        print(f"REUSED_EXISTING verdict={j['status']} receipt={receipt_path}", flush=True)
        return
    ambient, source, prompt, control = prepare(folder)
    results = []
    for label, config in [("control", control), ("goldfish", PINNED)]:
        x = run_one(label, config, folder, prompt, ambient, source, args.timeout)
        results.append(x)
        print(json.dumps({"finished": label,
                          "status": x["status"], "elapsed_s": x["elapsed_s"],
                          "ambient_seen": x.get("ambient_marker_seen_in_answer"),
                          "source_seen": x.get("explicit_source_marker_seen_in_answer"),
                          "tools": x.get("tool_calls"),
                          "has_session_id": bool(x.get("session_id"))}),
              flush=True)
        if x["status"] != "COMPLETED":
            break
    valid = (len(results) == 2
             and all(x["status"] == "COMPLETED" for x in results)
             and results[0]["ambient_marker_seen_in_answer"] is True
             and results[1]["ambient_marker_seen_in_answer"] is False
             and all(x["explicit_source_marker_seen_in_answer"] for x in results)
             and all(x["tool_calls"] in (None, 0) for x in results)
             and results[0].get("session_id") != results[1].get("session_id"))
    receipt = {
        "schema": "cxpan.openclaw_goldfish_context_ab/0.1",
        "workflow_id": args.workflow_id,
        "status": "PASS_CONTROLLED_AB" if valid else "INCONCLUSIVE_OR_FAIL",
        "config_diff": "agents.defaults.contextInjection always vs never",
        "source_word_sha256": sha(source),
        "ambient_word_sha256": sha(ambient),
        "synthetic_cwd": str(folder),
        "tools_policy": "deny_all_tools",
        "results": results,
        "limitations": [
            "AGENTS.md synthetic injection A/B is only one potential context channel",
            "Source word in explicit user prompt is a positive control, not proof of isolation",
            "Temporary agent exec sessions do not prove actual system prompt is free of all ambient providers",
            "Model outputs can be nondeterministic; failure of positive control is inconclusive",
            "No permanent production config or service modifications"
        ],
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print("VERDICT=" + receipt["status"] + " RECEIPT=" + str(receipt_path), flush=True)


if __name__ == "__main__":
    main()
