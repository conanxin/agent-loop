#!/usr/bin/env python3
"""EGM Gate B2 session-history A/B for Hermes and OpenClaw, no production edits.

Uses synthetic words only. All raw model outputs remain under the user's private
~/.local/state/cx-pan/egm/<workflow-id>/; receipts contain only marker digests and
boolean observations. An explicit Hermes --resume is the positive control.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

WORDS = ("birch", "cobalt", "fern", "lantern", "otter", "rainbow", "willow",
         "delta", "harbor", "maple", "canyon", "tulip", "copper", "starlight",
         "meadow", "compass", "lilac", "walnut", "cedar", "stone", "ribbon")
HOME = Path.home()
BASE = HOME / ".local/state/cx-pan/egm"
HERMES = HOME / ".local/bin/hermes"
OPENCLAW = HOME / ".npm-global/bin/openclaw"
PINNED = HOME / ".openclaw/cxpan-p5-readonly.json5"


def digest(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def make_word():
    return "-".join(secrets.SystemRandom().sample(WORDS, 3))


def call_harness(engine, cwd, prompt_file, phase, session, budget):
    if engine == "hermes":
        cmd = [
            str(HERMES), "chat", "-Q", "--source", "tool",
            "--ignore-rules", "--in", str(cwd),
            "-t", "clarify", "--run-budget", str(budget - 8),
            "--format", "text", "--query-file", str(prompt_file),
        ]
        if phase == "resume":
            assert session and re.fullmatch(r"local-[a-z0-9]+", session)
            cmd.extend(["--resume", session])
    elif engine == "openclaw":
        # agent exec has no --resume option and each turn is headless.
        conf = PINNED.read_text(encoding="utf-8")
        if '"deny": ["*"]' not in conf or '"contextInjection": "never"' not in conf:
            raise RuntimeError("pinned config does not disable tools + injection")
        cmd = [
            str(OPENCLAW), "agent", "exec",
            "--config", str(PINNED), "--cwd", str(cwd),
            "--model", "minimax/MiniMax-M3.1-Flash",
            "--code-mode", "direct", "--local-model-lean",
            "--thinking", "adaptive", "--timeout", str(budget - 10),
            "--json", "--message-file", str(prompt_file)
        ]
        if phase == "resume":
            raise ValueError("openclaw agent exec cannot resume a prior session")
    else:
        raise ValueError("unknown engine")

    started = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=budget)
        elapsed = round(time.monotonic() - started, 3)
    except subprocess.TimeoutExpired:
        return {"phase": phase, "status": "TIMEOUT", "elapsed_s": budget,
                "exit_code": None, "answer": "", "session_id": None,
                "tools_evidence": "UNAVAILABLE"}
    if engine == "hermes":
        answer = p.stdout or ""
        ids = re.findall(r"(?m)^session_id:\s*(local-[a-z0-9]+)\s*$", p.stderr or "")
        session_id = ids[-1] if ids else None
        success = p.returncode == 0 and bool(answer.strip())
        tools_evidence = "NO_TOOLSETS_OTHER_THAN_CLARIFY"
    else:
        try:
            j = json.loads(p.stdout)
        except (TypeError, json.JSONDecodeError):
            j = {}
        answer = j.get("final") or "\n".join(
            v.get("text", "") for v in j.get("payloads", [])
            if isinstance(v, dict) and isinstance(v.get("text"), str))
        session_id = j.get("sessionId")
        success = p.returncode == 0 and j.get("ok") is True and j.get("status") == "ok"
        tools = j.get("toolSummary")
        tools_evidence = (tools.get("calls") if isinstance(tools, dict)
                          else "NOT_IN_ENVELOPE")
    return {"phase": phase, "status": "COMPLETED" if success else "FAILED",
            "elapsed_s": elapsed, "exit_code": p.returncode,
            "answer": answer, "session_id": session_id,
            "tools_evidence": tools_evidence,
            "stderr_chars": len(p.stderr or "")}


def run(engine, workflow_id, budget):
    if not re.fullmatch(r"egm-b2-[a-zA-Z0-9-]{8,80}", workflow_id):
        raise ValueError("invalid workflow id")
    if not 35 <= budget <= 170:
        raise ValueError("budget must be 35..170 seconds")
    folder = BASE / workflow_id
    receipt_path = folder / "receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        print(json.dumps({"status": "REUSED_EXISTING",
                          "verdict": receipt["verdict"],
                          "receipt": str(receipt_path)}, ensure_ascii=False), flush=True)
        return
    if folder.exists() and any(folder.iterdir()):
        raise RuntimeError("Incomplete previous experiment: inspect before rerunning")
    folder.mkdir(parents=True, exist_ok=True)
    history_word, source_word = make_word(), make_word()
    while history_word == source_word:
        source_word = make_word()
    source_prompt = (
        "You are in a controlled test: reply with exactly the line OK_SEEDED, "
        "no commentary. A user in THIS session has told you that "
        "SESSION_HISTORY_WORD is " + history_word + "."
    )
    fresh_prompt = (
        "This is a controlled session-history test. "
        "Do not call tools. Reply with exactly 2 lines:\n"
        "SOURCE_WORD=" + source_word + "\n"
        "SESSION_HISTORY_WORD=<the word that the user earlier provided "
        "in the CURRENT conversation, otherwise NONE>.\n"
        "Never guess an unknown value. Only look at this conversation "
        "history, not any workspace file."
    )
    (folder / "seed.txt").write_text(source_prompt, encoding="utf-8")
    (folder / "question.txt").write_text(fresh_prompt, encoding="utf-8")
    phases = ["seed", "resume", "fresh"] if engine == "hermes" else ["seed", "fresh"]
    rows = []
    sid = None
    for phase in phases:
        prompt_file = folder / ("seed.txt" if phase == "seed" else "question.txt")
        ret = call_harness(engine, folder, prompt_file, phase, sid, budget)
        text = ret.pop("answer")
        (folder / (phase + ".answer.txt")).write_text(text, encoding="utf-8")
        row = dict(ret, answer_chars=len(text), answer_sha256=digest(text),
                   source_marker_seen=source_word in text if phase != "seed" else None,
                   history_marker_seen=history_word in text if phase != "seed" else None)
        rows.append(row)
        print(json.dumps({"phase": phase, "status": ret["status"],
                          "session_id": ret.get("session_id"),
                          "history_seen": row["history_marker_seen"],
                          "source_seen": row["source_marker_seen"],
                          "elapsed_s": ret["elapsed_s"]}), flush=True)
        if ret["status"] != "COMPLETED":
            break
        if phase == "seed":
            sid = ret.get("session_id")
            if not sid:
                break
    if engine == "hermes":
        verdict = (
            "PASS_CONTROLLED_HISTORY"
            if len(rows) == 3
            and all(x["status"] == "COMPLETED" for x in rows)
            and rows[1]["history_marker_seen"]
            and not rows[2]["history_marker_seen"]
            and rows[1]["source_marker_seen"]
            and rows[2]["source_marker_seen"]
            and rows[0]["session_id"] == rows[1]["session_id"]
            and rows[0]["session_id"] != rows[2]["session_id"]
            else "INCONCLUSIVE_OR_FAIL"
        )
    else:
        # Without an explicit resume positive control, this cannot establish full
        # history isolation; a clean headless two-turn experiment is only supporting.
        valid = (len(rows) == 2 and all(x["status"] == "COMPLETED" for x in rows)
                 and rows[1]["source_marker_seen"]
                 and not rows[1]["history_marker_seen"]
                 and rows[0]["session_id"] != rows[1]["session_id"])
        verdict = "SUPPORTING_FRESH_RUN_ONLY" if valid else "INCONCLUSIVE_OR_FAIL"
    receipt = {
        "schema": "cxpan.egm_history_ab/0.1", "engine": engine,
        "workflow_id": workflow_id, "verdict": verdict,
        "history_word_sha256": digest(history_word),
        "source_word_sha256": digest(source_word),
        "has_explicit_history_resume_positive_control": engine == "hermes",
        "raw_responses_local_only": True,
        "results": rows,
        "limitations": [
            "Only synthetic session word; not a proof against every memory provider or system prompt",
            "Fresh model non-disclosure by itself is weaker evidence than a positive/negative control",
            "Full effective prompt and every tool call require runtime trace instrumentation",
        ],
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print("VERDICT=" + verdict + " receipt=" + str(receipt_path), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=["hermes", "openclaw"])
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--budget", type=int, default=95)
    args = parser.parse_args()
    run(args.engine, args.workflow_id, args.budget)
