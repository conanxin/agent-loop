#!/usr/bin/env python3
"""Isolated P3 workflow tests. No network, no model/provider use."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
spec = importlib.util.spec_from_file_location("cxpan_workflow_test", ROOT / "bridge/workflow.py")
wf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wf)


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = Path(temp.name)
        prev = wf.STATE_DIR
        wf.STATE_DIR = self.state
        self.addCleanup(lambda: setattr(wf, "STATE_DIR", prev))
        self.sent = []
        self.tasks = {}

    def fake_request(self, method, path, payload=None):
        if method == "POST" and path == "/v1/tasks":
            key = payload["idempotency_key"]
            self.sent.append(key)
            if key in self.tasks:
                return {"duplicate": True, "task": {"task_id": self.tasks[key]}}
            tid = "task-" + str(len(self.tasks) + 1)
            self.tasks[key] = tid
            return {"duplicate": False, "task": {"task_id": tid}}
        if method == "GET" and path.endswith("/result"):
            tid = path.split("/")[3]
            return {
                "task": {"task_id": tid, "status": "COMPLETED", "run_id": tid + "-run",
                         "execution_health": "FINISHED"},
                "result_text": "verified result for " + tid, "error_text": ""
            }
        raise AssertionError(f"unexpected {method} {path}")

    def args(self, **kw):
        return SimpleNamespace(workflow_id="fixed-workflow-01", with_claude=False,
                               stage_timeout=20, poll=1, **kw)

    def test_three_stages_and_resumable_keys(self):
        with patch.object(wf, "request_json", side_effect=self.fake_request):
            self.assertEqual(wf.run(self.args()), 0)
            self.assertEqual(wf.run(self.args()), 0)
        self.assertEqual(len(self.tasks), 3)
        data = json.loads((self.state / "fixed-workflow-01.json").read_text())
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(len(data["stages"]), 3)
        self.assertEqual(
            [x["name"] for x in data["stages"]],
            ["repository_validation", "hermes_gateway", "openclaw_gateway"]
        )
        self.assertEqual(len(self.sent), 6)  # 3 are idempotent duplicate submits

    def test_claude_first_still_uses_explicit_sequential_stages(self):
        a = self.args()
        a.with_claude = True
        with patch.object(wf, "request_json", side_effect=self.fake_request):
            self.assertEqual(wf.run(a), 0)
        data = json.loads((self.state / "fixed-workflow-01.json").read_text())
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(len(data["stages"]), 4)
        self.assertEqual(data["stages"][0]["name"], "claude_readonly_research")

    def test_failed_model_stops_without_retrying(self):
        def fail_request(method, path, payload=None):
            if method == "POST":
                return {"duplicate": False, "task": {"task_id": "bad-agent"}}
            return {"task": {"status": "FAILED", "run_id": "err1",
                             "execution_health": "FINISHED"},
                    "result_text": "", "error_text": "provider unavailable"}
        a = self.args()
        a.with_claude = True
        with patch.object(wf, "request_json", side_effect=fail_request) as fn:
            self.assertEqual(wf.run(a), 1)
        self.assertEqual(fn.call_count, 2)
        self.assertEqual(
            json.loads((self.state / "fixed-workflow-01.json").read_text())["status"],
            "FAILED"
        )

    def test_inconsistent_stage_selection_is_rejected(self):
        with patch.object(wf, "request_json", side_effect=self.fake_request):
            self.assertEqual(wf.run(self.args()), 0)
        b = self.args()
        b.with_claude = True
        with self.assertRaises(ValueError):
            wf.run(b)


if __name__ == "__main__":
    unittest.main()
