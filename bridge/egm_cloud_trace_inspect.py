#!/usr/bin/env python3
"""Read-only SQLite trace summary for a bounded OpenClaw EGM B2 experiment.

Does not expose prompts or tool arguments; reports structure, tool-schema names,
tool-call event counts, and usage. Empty audit tables are not proof of no calls.
"""
import argparse
import hashlib
from collections import Counter
import json
from pathlib import Path
import sqlite3

BASE = Path.home() / ".local/state/cx-pan/egm"


def inspect_experiment(root):
    receipt_path = root / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    sid = receipt.get("session_id")
    if not sid:
        raise ValueError("receipt has no model session id")
    agent_db = root / "state/agents/main/agent/openclaw-agent.sqlite"
    main_db = root / "state/state/openclaw.sqlite"
    if not agent_db.exists() or not main_db.exists():
        raise FileNotFoundError("retained-state SQLite files are required")
    agent = sqlite3.connect(f"file:{agent_db}?mode=ro", uri=True, timeout=4)
    parent = sqlite3.connect(f"file:{main_db}?mode=ro", uri=True, timeout=4)
    transcript_type = Counter()
    content_type = Counter()
    trajectory_type = Counter()
    exposed_tools = set()
    tool_call_blocks = 0
    tool_metadata_records = 0
    session_declared_tool_count = None
    client_tool_count = None
    usage = {}
    run_id = None
    compiled_prior_messages = None
    submitted_prior_messages = None
    compiled_system_prompt_sha256 = None
    compiled_system_prompt_characters = None
    try:
        for (blob,) in agent.execute(
            "SELECT event_json FROM transcript_events WHERE session_id=? ORDER BY seq", (sid,)
        ):
            try: j = json.loads(blob)
            except ValueError: continue
            typ = str(j.get("type") or "unknown")
            transcript_type[typ] += 1
            msg = j.get("message") if isinstance(j.get("message"), dict) else {}
            blocks = msg.get("content") if isinstance(msg.get("content"), list) else []
            for block in blocks:
                if not isinstance(block, dict):continue
                btyp = str(block.get("type") or "unknown")
                content_type[btyp] += 1
                if btyp in ("toolCall", "toolResult", "tool_use", "tool_result"):
                    tool_call_blocks += 1
        for run, blob in agent.execute(
            "SELECT run_id,event_json FROM trajectory_runtime_events WHERE session_id=? ORDER BY seq",
            (sid,)
        ):
            run_id = run
            try:j = json.loads(blob)
            except ValueError:continue
            typ = str(j.get("type") or "unknown")
            trajectory_type[typ] += 1
            d = j.get("data") if isinstance(j.get("data"), dict) else {}
            if typ == "session.started":
                session_declared_tool_count = d.get("toolCount")
                client_tool_count = d.get("clientToolCount")
            elif typ == "context.compiled":
                compiled_prior_messages = (len(d.get("messages"))
                                           if isinstance(d.get("messages"), list) else None)
                system = d.get("systemPrompt")
                if isinstance(system, str):
                    compiled_system_prompt_sha256 = hashlib.sha256(
                        system.encode("utf-8")).hexdigest()
                    compiled_system_prompt_characters = len(system)
                schemas = d.get("tools")
                if isinstance(schemas, list):
                    for item in schemas:
                        if isinstance(item, dict) and isinstance(item.get("name"), str):
                            exposed_tools.add(item["name"])
            elif typ == "prompt.submitted":
                submitted_prior_messages = (len(d.get("messages"))
                                            if isinstance(d.get("messages"), list) else None)
            elif typ == "trace.artifacts":
                metas = d.get("toolMetas")
                tool_metadata_records = len(metas) if isinstance(metas, list) else 0
                u = d.get("usage")
                if isinstance(u, dict):
                    usage = {k:v for k,v in u.items() if k in (
                        "input", "output", "cacheRead", "cacheWrite", "total"
                    ) and isinstance(v,(int,float))}
        audits = parent.execute(
            "SELECT COUNT(*), COUNT(tool_call_id) FROM audit_events WHERE session_id=?",
            (sid,)
        ).fetchone()
        outcome_count = (agent.execute(
            "SELECT COUNT(*) FROM message_tool_run_outcomes WHERE run_id=?", (run_id,)
        ).fetchone()[0] if run_id else 0)
    finally:
        agent.close()
        parent.close()
    return {
        "schema": "cxpan.egm_cloud_sqlite_trace/0.1",
        "session_id": sid,
        "experiment": root.name,
        "experiment_status": receipt.get("status"),
        "transcript_event_types": dict(transcript_type),
        "content_block_types": dict(content_type),
        "trajectory_event_types": dict(trajectory_type),
        "transcript_tool_blocks": tool_call_blocks,
        "runtime_tool_metadata_records": tool_metadata_records,
        "tool_run_outcome_rows": outcome_count,
        "audit_event_rows": audits[0],
        "audit_tool_call_id_rows": audits[1],
        "compiled_tool_schema_names": sorted(exposed_tools),
        "session_declared_tool_count": session_declared_tool_count,
        "client_tool_count": client_tool_count,
        "usage_tokens": usage,
        "compiled_prior_message_count": compiled_prior_messages,
        "submitted_prior_message_count": submitted_prior_messages,
        "compiled_system_prompt_sha256": compiled_system_prompt_sha256,
        "compiled_system_prompt_characters": compiled_system_prompt_characters,
        "scope_limitations": [
            "Empty trace tool events support zero observed calls only for this run.",
            "Exposed tool schemas are not the same as executed or authorized tools.",
            "No raw model prompt, response, arguments, or credentials exported."
        ],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    args = p.parse_args()
    root = BASE / args.name
    if root.parent != BASE:
        raise ValueError("invalid experiment root")
    summary = inspect_experiment(root)
    target = root / "sqlite-trace-summary.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
