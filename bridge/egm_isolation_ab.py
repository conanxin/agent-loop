#!/usr/bin/env python3
"""Controlled Hermes Goldfish context-file isolation A/B experiment.

Only writes test assets under ~/.local/state/cx-pan/egm/gate-b-... .
No production services, gateway settings, or repository content is mutated.
Use a randomly generated canary; never print it or upload it to Git/Notion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

HOME = Path.home()
HERMES = HOME / ".local/bin/hermes"
BASE = HOME / ".local/state/cx-pan/egm"


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def run_one(label, folder, prompt, ignore_rules, timeout):
    cmd = [str(HERMES), "chat", "-Q", "--in", str(folder),
           "--source", "tool", "-t", "clarify",
           "--format", "text", "--run-budget", str(timeout - 8)]
    if ignore_rules:
        cmd.append("--ignore-rules")
    cmd += ["--query-file", str(prompt)]
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=timeout)
        return {
            "label": label, "exit_code": proc.returncode,
            "elapsed_s": round(time.monotonic() - started, 3),
            "stdout": proc.stdout or "", "stderr": proc.stderr or "",
            "status": "COMPLETED" if proc.returncode == 0 else "FAILED"
        }
    except subprocess.TimeoutExpired:
        return {"label": label, "exit_code": None, "elapsed_s": timeout,
                "stdout": "", "stderr": "", "status": "TIMEOUT"}


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=True)
    lexicon = ["birch", "cobalt", "fern", "lantern", "otter", "rainbow", "willow", "delta", "harbor", "maple", "canyon", "tulip", "copper", "starlight", "meadow", "compass"]
    ambient = "-".join(secrets.SystemRandom().sample(lexicon, 3))
    source = "-".join(secrets.SystemRandom().sample(lexicon, 3))
    while source == ambient:
        source = "-".join(secrets.SystemRandom().sample(lexicon, 3))
    (folder / "AGENTS.md").write_text(
        "# Controlled context-injection marker for EGM-R2\n"
        "This is a synthetic, non-secret project instruction for a controlled test.\n"
        "If asked about AMBIENT_WORD, its value is exactly "
        + ambient + ".\n", encoding="utf-8")
    prompt = folder / "goldfish-question.txt"
    prompt.write_text(
        "Answer only in exactly two lines. This is a controlled isolation test.\n"
        "SOURCE_WORD=" + source + "\n"
        "AMBIENT_WORD=<copy the value from injected project "
        "instructions if actually visible, otherwise NONE>\n"
        "Do not call tools, do not inspect files, do not guess the ambient token.\n",
        encoding="utf-8")
    return ambient, source, prompt


def summarize(result, ambient, source, folder):
    label = result["label"]
    (folder / (label + ".stdout.txt")).write_text(result.pop("stdout"), encoding="utf-8")
    (folder / (label + ".stderr.txt")).write_text(result.pop("stderr"), encoding="utf-8")
    output = (folder / (label + ".stdout.txt")).read_text(encoding="utf-8")
    result["ambient_marker_seen_in_answer"] = ambient in output
    result["explicit_source_marker_seen_in_answer"] = source in output
    result["model_text_chars"] = len(output)
    result["stdout_sha256"] = sha(output)
    result["canary_not_written_to_public_report"] = True
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workflow-id", required=True)
    p.add_argument("--timeout", type=int, default=90)
    a = p.parse_args()
    if not a.workflow_id.startswith("egm-b-") or not a.workflow_id.replace("-", "").isalnum():
        p.error("workflow ID must start egm-b- and contain only ASCII letters/numbers/hyphens")
    if not 40 <= a.timeout <= 150:
        p.error("timeout must be 40..150s")
    folder = BASE / a.workflow_id
    receipt_file = folder / "receipt.json"
    if receipt_file.exists():
        existing = json.loads(receipt_file.read_text(encoding="utf-8"))
        print(json.dumps({"status": "REUSED_EXISTING", "path": str(receipt_file),
                          "results": existing["results"]}, ensure_ascii=False), flush=True)
        return
    ambient, source, prompt = prepare(folder)
    results = []
    # Positive control: ordinary chat can see project's AGENTS.md if injected.
    # Strict treatment: same cwd and user prompt, but ignores rules/memory.
    for label, strict in [("control", False), ("goldfish", True)]:
        outcome = summarize(run_one(label, folder, prompt, strict, a.timeout),
                            ambient, source, folder)
        results.append(outcome)
        print(json.dumps({"finished": label, "status": outcome["status"],
                          "ambient_seen": outcome["ambient_marker_seen_in_answer"],
                          "source_seen": outcome["explicit_source_marker_seen_in_answer"],
                          "elapsed_s": outcome["elapsed_s"]}, ensure_ascii=False), flush=True)
        if outcome["status"] != "COMPLETED":
            break
    verdict = (
        "PASS_CONTROLLED_AB" if len(results) == 2 and all(x["status"] == "COMPLETED" for x in results)
        and results[0]["ambient_marker_seen_in_answer"]
        and not results[1]["ambient_marker_seen_in_answer"]
        and all(x["explicit_source_marker_seen_in_answer"] for x in results)
        else "INCONCLUSIVE_OR_FAIL"
    )
    receipt = {
        "schema": "cxpan.egm_isolation_ab/0.1",
        "workflow_id": a.workflow_id,
        "mode": "controlled_AGENTS_marker_only",
        "status": verdict,
        "canary_digest": sha(ambient),
        "source_marker_digest": sha(source),
        "marker_not_in_user_prompt": True,
        "fresh_cli_invocations": len(results),
        "no_resume_flag": True,
        "strict_mode_flags": ["chat", "-Q", "--ignore-rules", "--source", "tool", "-t", "clarify"],
        "results": results,
        "limits": [
            "A/B only probes one AGENTS.md synthetic marker, not all ambient sources",
            "Model responses alone do not establish the complete effective system prompt",
            "Session persistence and memory/history leakage require further direct trace audit",
            "Positive-control failure leaves the test inconclusive, not a strict isolation success"
        ]
    }
    receipt_file.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print("VERDICT=" + verdict + " receipt=" + str(receipt_file), flush=True)


if __name__ == "__main__":
    main()
