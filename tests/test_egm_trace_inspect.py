#!/usr/bin/env python3
"""Offline tests for SQLite-based B2 OpenClaw runtime trace auditing."""
import json
import subprocess
from unittest.mock import patch
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from egm_cloud_trace_inspect import inspect_experiment
import egm_cloud_trace_probe as probe


def sample(root, with_call=False):
    (root / "state/agents/main/agent").mkdir(parents=True)
    (root / "state/state").mkdir(parents=True)
    (root / "receipt.json").write_text(json.dumps({
        "session_id": "test-fresh-uuid", "status": "COMPLETED"
    }), encoding="utf8")
    agent = sqlite3.connect(root/"state/agents/main/agent/openclaw-agent.sqlite")
    agent.execute("CREATE TABLE transcript_events (session_id TEXT, event_json TEXT, seq INT)")
    agent.execute("CREATE TABLE trajectory_runtime_events (session_id TEXT, run_id TEXT, event_json TEXT, seq INT)")
    agent.execute("CREATE TABLE message_tool_run_outcomes (run_id TEXT, outcome TEXT)")
    records = [
        {"type": "session"},
        {"type": "message", "message": {"role": "user", "content": "test"}},
        {"type": "message", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "done"}] +
            ([{"type": "toolCall", "name": "tool_search"}] if with_call else [])}}
    ]
    for i, obj in enumerate(records):
        agent.execute("INSERT INTO transcript_events VALUES (?,?,?)",
                      ("test-fresh-uuid", json.dumps(obj), i))
    events = [
        ("session.started", {"toolCount": 3, "clientToolCount": 0}),
        ("context.compiled", {"tools": [{"name":"tool_call"},
                                       {"name":"tool_describe"},
                                       {"name":"tool_search"}]}),
        ("trace.artifacts", {"toolMetas": [], "usage":{
            "input":11, "output":7, "total":18}}),
    ]
    for i,(type_, data) in enumerate(events):
        agent.execute("INSERT INTO trajectory_runtime_events VALUES (?,?,?,?)",
                      ("test-fresh-uuid", "run-001",
                       json.dumps({"type":type_, "data":data}), i))
    agent.commit()
    agent.close()
    state = sqlite3.connect(root/"state/state/openclaw.sqlite")
    state.execute("CREATE TABLE audit_events (session_id TEXT, tool_call_id TEXT)")
    state.commit()
    state.close()


class SQLiteTraceInspectorTest(unittest.TestCase):

    def test_exposed_tools_are_not_assumed_executed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sample(root,False)
            result = inspect_experiment(root)
            self.assertEqual(result["compiled_tool_schema_names"],
                             ["tool_call", "tool_describe", "tool_search"])
            self.assertEqual(result["session_declared_tool_count"],3)
            self.assertEqual(result["transcript_tool_blocks"],0)
            self.assertEqual(result["runtime_tool_metadata_records"],0)
            self.assertEqual(result["audit_tool_call_id_rows"],0)
            self.assertEqual(result["usage_tokens"]["input"],11)

    def test_tool_call_event_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sample(root,True)
            result=inspect_experiment(root)
            self.assertEqual(result["transcript_tool_blocks"],1)
            self.assertEqual(result["content_block_types"]["toolCall"],1)


    def test_temporary_tool_search_disable_does_not_edit_pinned_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            configs=root/".openclaw"
            configs.mkdir()
            pinned=configs/"read-only.json5"
            original=('{"$include": "./openclaw.json", "tools": {"deny": ["*"]}, '
                      '"agents": {"defaults": {"contextInjection": "never"}}}')
            pinned.write_text(original,encoding="utf-8")
            captured={}
            def fake_model(cmd,**kwargs):
                conf=Path(cmd[cmd.index("--config")+1])
                captured["effective_conf"]=conf.read_text(encoding="utf-8")
                return subprocess.CompletedProcess([],0,json.dumps({
                    "ok":True,"status":"ok","final":"NO_TOOL_AVAILABLE",
                    "sessionId":"synthetic-session"}),"")
            with patch.object(probe,"BASE",root),patch.object(
                probe,"PINNED",pinned),patch.object(probe.subprocess,"run",side_effect=fake_model):
                probe.run("egm-b2-test-notoolsearch",80,True,True)
            self.assertIn('"toolSearch": false',captured["effective_conf"])
            self.assertIn('"deny": ["*"]',captured["effective_conf"])
            self.assertEqual(pinned.read_text(encoding="utf-8"),original)

    def test_mandatory_sqlite_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            root.joinpath("receipt.json").write_text(json.dumps({
                "session_id":"uuid", "status":"COMPLETED"
            }))
            with self.assertRaises(FileNotFoundError):
                inspect_experiment(root)


if __name__ == "__main__":
    unittest.main()
