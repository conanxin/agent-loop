#!/usr/bin/env python3
"""Offline tests for B2 session-boundary and retained trace probes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import egm_history_ab as history
import egm_cloud_trace_probe as trace


class HistoryBoundaryTest(unittest.TestCase):
    def test_hermes_explicit_resume_only_in_resume_phase(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "prompt.txt"
            p.write_text("Test")
            resp = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="SOURCE_WORD=fern-maple-birch",
                stderr="session_id: local-abc123\n")
            with patch.object(history, "HERMES", Path("/bin/true")), patch.object(
                history.subprocess, "run", return_value=resp
            ) as proc:
                history.call_harness("hermes", root, p, "fresh", None, 95)
                fresh_cmd = proc.call_args.args[0]
                history.call_harness("hermes", root, p, "resume", "local-abc123", 95)
                resume_cmd = proc.call_args.args[0]
            self.assertIn("--ignore-rules", fresh_cmd)
            self.assertNotIn("--resume", fresh_cmd)
            self.assertEqual(resume_cmd[-2:], ["--resume", "local-abc123"])
            self.assertNotIn("-z", fresh_cmd)

    def test_openclaw_no_resume_and_config_is_deny_all(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prompt = root / "q.txt"
            prompt.write_text("Trace")
            conf = root / "config.json5"
            conf.write_text('{"tools":{"deny": ["*"]},"agents":{"defaults":{"contextInjection": "never"}}}')
            data = {"ok": True, "status": "ok", "final": "SOURCE_WORD=fern",
                    "sessionId": "abcd-unique-uuid"}
            response = subprocess.CompletedProcess([], 0, json.dumps(data), "")
            with patch.object(history, "PINNED", conf), patch.object(
                history.subprocess, "run", return_value=response
            ) as proc:
                result = history.call_harness("openclaw", root, prompt, "fresh", None, 90)
                args = proc.call_args.args[0]
                self.assertEqual(result["status"], "COMPLETED")
                self.assertEqual(result["session_id"], "abcd-unique-uuid")
                self.assertIn("--json", args)
                self.assertNotIn("--resume", args)
                with self.assertRaisesRegex(ValueError, "cannot resume"):
                    history.call_harness("openclaw", root, prompt, "resume", "old-session", 90)

    def test_workflow_receipt_reuse_requires_no_model_invocation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            name = "egm-b2-example-history"
            folder = root/name
            folder.mkdir()
            (folder/"receipt.json").write_text(json.dumps({"verdict": "PASS_CONTROLLED_HISTORY"}))
            with patch.object(history, "BASE", root), patch.object(
                history, "call_harness"
            ) as model:
                history.run("hermes", name, 70)
            model.assert_not_called()

    def test_result_without_resume_positive_control_cannot_claim_full_history_pass(self):
        self.assertNotIn("resume", ["seed", "fresh"])
        self.assertIn("resume", ["seed", "resume", "fresh"])


class TraceAuditTest(unittest.TestCase):
    def test_jsonl_records_count_actual_tool_blocks_without_text_leak(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"sessions.jsonl"
            p.write_text("\n".join([
                json.dumps({"type": "message", "message": {"role": "user", "content": "hello"}}),
                json.dumps({"type": "message", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "answer"},
                    {"type": "toolCall", "name": "fake", "arguments": {}}]}})
            ])+"\n")
            result = trace.summarize_jsonl(p)
            self.assertEqual(result["lines"], 2)
            self.assertEqual(result["roles"]["assistant"], 1)
            self.assertEqual(result["tool_call_records"], 1)
            self.assertNotIn("answer", json.dumps(result))

    def test_trace_reuse_prevents_second_model_run(self):
        with tempfile.TemporaryDirectory() as d:
            name = "egm-b2-example-trace"
            folder=Path(d)/name
            folder.mkdir()
            (folder/"receipt.json").write_text(json.dumps({"status":"COMPLETED"}))
            with patch.object(trace,"BASE",Path(d)),patch.object(
                trace.subprocess,"run"
            ) as sp:
                trace.run(name,80)
            sp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
