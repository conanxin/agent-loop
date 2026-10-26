#!/usr/bin/env python3
"""P4 cross-agent handoff contract; isolated and network-free."""
import importlib.util
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
spec = importlib.util.spec_from_file_location("cxpan_handoff_test", ROOT / "bridge/handoff.py")
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)

SOURCE = "c520ab0b-778b-4eb3-8508-ec8909cba422"


class HandoffTest(unittest.TestCase):
    def test_completed_claude_handoff_is_bounded_and_idempotent(self):
        calls = []

        def query(method, path, data=None):
            calls.append((method, path, data))
            if method == "GET":
                return {
                    "task": {
                        "target": "claude.code.local",
                        "status": "COMPLETED",
                        "project_id": "CX-PAN",
                        "run_id": "claude-provenance-01",
                    },
                    "result_text": "Claude claimed:\n" + "X" * 6000
                }
            return {
                "task": {"task_id": "new-hermes-task"},
                "duplicate": False
            }

        response = handoff.make_handoff(SOURCE, query=query)
        self.assertFalse(response["duplicate"])
        self.assertEqual([x[0] for x in calls], ["GET", "POST"])
        self.assertEqual(calls[0][1], f"/v1/tasks/{SOURCE}/result")
        request = calls[1][2]
        self.assertEqual(request["idempotency_key"], f"p5-claude-hermes-provenance-{SOURCE}")
        self.assertEqual(request["parent_task_id"], SOURCE)
        expected = "Claude claimed:\n" + "X" * 6000
        self.assertEqual(request["source_sha256"],
                         hashlib.sha256(expected.encode("utf-8")).hexdigest())
        self.assertEqual(request["target"], "hermes.model.local")
        self.assertEqual(request["capability"], "text.review")
        self.assertEqual(request["repo_id"], "none")
        self.assertIn(SOURCE, request["goal"])
        self.assertIn("claude-provenance-01", request["goal"])
        self.assertTrue(len(request["goal"]) <= 3000)

    def test_reject_failed_upstream_task(self):
        def query(*args, **kwargs):
            return {
                "task": {
                    "target": "claude.code.local",
                    "status": "FAILED", "project_id": "CX-PAN"
                }, "result_text": "not valid"
            }
        with self.assertRaisesRegex(ValueError, "only a completed"):
            handoff.make_handoff(SOURCE, query=query)

    def test_reject_non_claude_source(self):
        def query(*args, **kwargs):
            return {
                "task": {
                    "target": "echo.local",
                    "status": "COMPLETED", "project_id": "CX-PAN"
                }, "result_text": "echo text"
            }
        with self.assertRaisesRegex(ValueError, "only a completed"):
            handoff.make_handoff(SOURCE, query=query)

    def test_reject_invalid_task_identifier(self):
        with self.assertRaises(ValueError):
            handoff.make_handoff("../etc/passwd", query=lambda *args: None)


if __name__ == "__main__":
    unittest.main()
