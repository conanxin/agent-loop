#!/usr/bin/env python3
"""Offline integrity/safety tests for B3-R3 bounded OpenClaw diagnostics."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
MODULE=HERE/"benchmarks/egm_b3_r3/probe_model.py"
source=importlib.util.spec_from_file_location("egm_probe_model_b3r3",MODULE)
probe=importlib.util.module_from_spec(source)
source.loader.exec_module(probe)
FIXTURES=HERE/"benchmarks/egm_b3_r2"


class GateB3R3ProbeTest(unittest.TestCase):
    def make_env(self,root):
        config=root/"openclaw"/"pinned.json5"
        config.parent.mkdir()
        config.write_text('{"$include":"./openclaw.json","tools":{"deny": ["*"]},'
                          '"agents":{"defaults":{"contextInjection": "never"}}}',encoding="utf-8")
        return config

    def test_reuse_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            folder=base/"egm-b3r3-test-repeat1"
            folder.mkdir()
            (folder/"receipt.json").write_text(json.dumps({"status":"COMPLETED"}))
            with patch.object(probe,"BASE",base),patch.object(
                probe.subprocess,"run"
            ) as fake:
                probe.run("egm-b3r3-test-repeat1",FIXTURES,
                          "p6-evidence-integrity","minimax/MiniMax-M2.7",60)
            fake.assert_not_called()

    def test_incomplete_existing_workflow_is_never_retried(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            folder=base/"egm-b3r3-test-incomplete"
            folder.mkdir()
            (folder/"prompt.txt").write_text("incomplete")
            with patch.object(probe,"BASE",base),patch.object(
                probe.subprocess,"run"
            ) as fake:
                with self.assertRaisesRegex(RuntimeError,"Incomplete prior"):
                    probe.run("egm-b3r3-test-incomplete",FIXTURES,
                              "p6-evidence-integrity","minimax/MiniMax-M2.7",60)
            fake.assert_not_called()

    def test_rejects_unknown_model_and_source(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            with patch.object(probe,"BASE",base):
                with self.assertRaisesRegex(ValueError,"allowlisted"):
                    probe.run("egm-b3r3-test-other",FIXTURES,
                              "p6-evidence-integrity","ollama/qwen3",60)
                with self.assertRaisesRegex(ValueError,"allowlisted"):
                    probe.run("egm-b3r3-test-wrong",FIXTURES,
                              "secret-file","minimax/MiniMax-M2.7",60)

    def test_success_stays_tool_free_and_frozen_source_sha(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            config=self.make_env(base)
            fake_envelope={
                "ok":True,"status":"ok","final":'{"status":"UNKNOWN","issue":"none","ref":""}',
                "sessionId":"synthetic-diagnostic-session"
            }
            event=subprocess.CompletedProcess([],0,json.dumps(fake_envelope),"")
            with patch.object(probe,"BASE",base),patch.object(
                probe,"PINNED",config
            ),patch.object(probe.subprocess,"run",return_value=event) as mock:
                probe.run("egm-b3r3-success-case",FIXTURES,
                          "p6-evidence-integrity","minimax/MiniMax-M2.7",60)
                cmd=mock.call_args.args[0]
                self.assertIn("--state-dir",cmd)
                self.assertIn("--message-file",cmd)
                self.assertNotIn("--resume",cmd)
                conf=Path(cmd[cmd.index("--config")+1])
                self.assertEqual(conf.parent,config.parent)
                self.assertFalse(conf.exists())
                self.assertIn("--model",cmd)
                self.assertEqual(cmd[cmd.index("--model")+1],"minimax/MiniMax-M2.7")
                self.assertEqual(mock.call_args.kwargs["timeout"],60)
            receipt=json.loads((base/"egm-b3r3-success-case/receipt.json").read_text())
            self.assertEqual(receipt["status"],"COMPLETED")
            self.assertEqual(receipt["trace"]["tool_call_events"],0)
            case=next(c for c in json.loads((FIXTURES/"manifest_compact.json").read_text())["cases"]
                      if c["case_id"]=="p6-evidence-integrity")
            self.assertEqual(receipt["source_sha256"],case["packet_sha256"])
            self.assertIn('"deny": ["*"]',config.read_text())
            self.assertNotIn("toolSearch",config.read_text())

    def test_model_thinking_preflight_rejects_invalid_combinations(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            with patch.object(probe,"BASE",base),patch.object(
                probe.subprocess,"run"
            ) as model:
                with self.assertRaisesRegex(ValueError,"model-thinking-level mismatch"):
                    probe.run("egm-b3r3-m27-adaptive",FIXTURES,
                              "p6-evidence-integrity","minimax/MiniMax-M2.7",60,
                              thinking="adaptive")
                with self.assertRaisesRegex(ValueError,"model-thinking-level mismatch"):
                    probe.run("egm-b3r3-flash-low",FIXTURES,
                              "p6-evidence-integrity","minimax/MiniMax-M3.1-Flash",60,
                              thinking="low")
            model.assert_not_called()
            self.assertFalse((base/"egm-b3r3-m27-adaptive").exists())

    def test_explicit_m27_medium_thinking_is_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);config=self.make_env(base)
            model_response={"ok":True,"status":"ok","final":"UNKNOWN", "sessionId":"synthetic"}
            with patch.object(probe,"BASE",base),patch.object(
                probe,"PINNED",config
            ),patch.object(probe.subprocess,"run",return_value=subprocess.CompletedProcess(
                [],0,json.dumps(model_response),"")) as model:
                probe.run("egm-b3r3-m27-medium",FIXTURES,
                          "p6-evidence-integrity","minimax/MiniMax-M2.7",60,
                          thinking="medium")
            cmd=model.call_args.args[0]
            self.assertEqual(cmd[cmd.index("--thinking")+1],"medium")
            receipt=json.loads((base/"egm-b3r3-m27-medium/receipt.json").read_text())
            self.assertEqual(receipt["thinking"],"medium")

    def test_timeout_no_model_completed_classification(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            config=self.make_env(root)
            def timeout(_cmd,**kwargs):
                raise subprocess.TimeoutExpired("model",60,b"",b"")
            with patch.object(probe,"BASE",root),patch.object(
                probe,"PINNED",config
            ),patch.object(probe.subprocess,"run",side_effect=timeout):
                probe.run("egm-b3r3-timeout-case",FIXTURES,
                          "p6-evidence-integrity","minimax/MiniMax-M2.7",60)
            receipt=json.loads((root/"egm-b3r3-timeout-case/receipt.json").read_text())
            self.assertEqual(receipt["status"],"TIMEOUT_NO_MODEL_COMPLETE")
            self.assertTrue(receipt["wall_timeout"])
            self.assertIsNone(receipt["raw_cli_exit"])

    def test_trace_reports_actual_model_and_compilation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"state.sqlite"
            db=sqlite3.connect(p)
            db.execute("CREATE TABLE trajectory_runtime_events (seq INTEGER,event_json TEXT)")
            for i,t in enumerate([
                {"type":"session.started","provider":"minimax","modelId":"MiniMax-M2.7"},
                {"type":"prompt.submitted"},
                {"type":"context.compiled","data":{"tools":[]}},
                {"type":"model.completed"},
                {"type":"trace.artifacts","data":{"usage":{"input":100,"output":25,"total":125}}}
            ]):
                db.execute("INSERT INTO trajectory_runtime_events VALUES (?,?)",(i,json.dumps(t)))
            db.execute("CREATE TABLE transcript_events (seq INTEGER)")
            db.execute("INSERT INTO transcript_events VALUES(0)")
            db.commit();db.close()
            status=probe.trace_status(p)
            self.assertEqual(status["actual_model"],"MiniMax-M2.7")
            self.assertTrue(status["model_completed_event"])
            self.assertTrue(status["prompt_submitted_event"])
            self.assertEqual(status["model_visible_tool_count"],0)
            self.assertEqual(status["usage_tokens"]["total"],125)


if __name__=="__main__":
    unittest.main()
