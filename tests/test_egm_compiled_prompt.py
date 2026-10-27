#!/usr/bin/env python3
"""Offline validation of the B2 compiled-system-prompt isolation experiment."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"bridge"))
import egm_cloud_prompt_ab as compiled


class CompiledPromptTest(unittest.TestCase):
    def test_compiled_and_submitted_marker_detection_only(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            p=root/"state/agents/main/agent"
            p.mkdir(parents=True)
            db=sqlite3.connect(p/"openclaw-agent.sqlite")
            db.execute("CREATE TABLE trajectory_runtime_events (session_id TEXT,event_json TEXT)")
            source="violet-maple-delta"
            ambient="cobalt-fern-lantern"
            rows=[
                {"type":"context.compiled","data":{
                    "systemPrompt":"system\n"+ambient,
                    "prompt":"user\n"+source,
                    "messages":[]
                }},
                {"type":"prompt.submitted","data":{
                    "systemPrompt":"system\n"+ambient,
                    "prompt":"user\n"+source,
                    "messages":[]
                }}
            ]
            for item in rows:
                db.execute("INSERT INTO trajectory_runtime_events VALUES (?,?)",
                           ("synthetic-session",json.dumps(item)))
            db.commit();db.close()
            out=compiled.state_trace(root,"synthetic-session",source,ambient)
            self.assertEqual(out["trace_status"],"FOUND_COMPILED_PROMPT")
            self.assertTrue(out["compiled_ambient_in_system"])
            self.assertFalse(out["compiled_source_in_system"])
            self.assertTrue(out["submitted_source_in_user"])
            self.assertFalse(out["submitted_ambient_in_user"])
            self.assertEqual(out["compiled_prior_message_count"],0)
            self.assertEqual(out["tool_call_events"],0)
            self.assertTrue(len(out["compiled_system_sha256"])==64)

    def test_missing_sqlite_is_inconclusive_not_pass(self):
        with tempfile.TemporaryDirectory() as t:
            summary=compiled.state_trace(Path(t),"absent","source","ambient")
            self.assertEqual(summary["trace_status"],"NO_SQLITE")

    def test_old_receipt_skips_model_calls(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"egm-b2-existing-prompt"
            p.mkdir()
            (p/"receipt.json").write_text(json.dumps({"verdict":"PASS_COMPILED_PROMPT_AB"}))
            with patch.object(compiled,"BASE",Path(t)),patch.object(
                compiled.subprocess,"run"
            ) as engine:
                compiled.run("egm-b2-existing-prompt",80)
            engine.assert_not_called()


if __name__=="__main__":
    unittest.main()
