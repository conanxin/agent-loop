#!/usr/bin/env python3
"""P2 worker local capability and error-path tests. No model is called."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
spec = importlib.util.spec_from_file_location("cxpan_worker_test", ROOT / "bridge/worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTest(unittest.TestCase):
    def test_health_adapter_only_uses_readonly_status_and_version(self):
        runs = [
            CompletedProcess(args=[], returncode=0, stdout="active\n", stderr=""),
            CompletedProcess(
                args=[], returncode=0,
                stdout="OpenClaw 2026.10.5 (1b58cb9)\n", stderr=""
            )
        ]
        with patch.object(worker.subprocess, "run", side_effect=runs) as mock_run:
            result, run_id = worker.read_gateway_health("openclaw.health.local")
        body = json.loads(result)
        self.assertEqual(body["gateway_state"], "active")
        self.assertFalse(body["model_invoked"])
        self.assertEqual(body["mode"], "read_only_health_check")
        self.assertTrue(run_id.startswith("health:"))
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(
            mock_run.call_args_list[0].args[0],
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"]
        )
        self.assertEqual(mock_run.call_args_list[1].args[0][-1], "--version")

    def test_fixed_repo_validation_uses_allowlisted_unittest_command(self):
        response = CompletedProcess(
            args=[], returncode=0, stdout="",
            stderr="Ran 24 tests in 2.100s\\n\\nOK\\n"
        )
        with patch.object(worker, "REPO", ROOT), patch.object(
            worker.subprocess, "run", return_value=response
        ) as run_mock:
            result, run_id = worker.validate_repo()
        doc = json.loads(result)
        self.assertEqual(doc["tests_run"], 24)
        self.assertEqual(doc["status"], "PASS")
        self.assertFalse(doc["model_invoked"])
        command = run_mock.call_args.args[0]
        self.assertEqual(command[1:], ["-m", "unittest", "discover", "-s", "tests", "-q"])
        self.assertTrue(run_id.startswith("verify:"))

    def test_claude_error_parses_only_safe_subtype_not_raw_content(self):
        task = {
            "target": "claude.code.local", "repo_id": "agent-loop",
            "goal": "Please inspect a harmless file."
        }
        response = CompletedProcess(
            args=[], returncode=1,
            stdout=json.dumps({
                "subtype": "error_during_execution",
                "result": "SENSITIVE_UNRELATED_TEXT"
            }),
            stderr=""
        )
        with patch.object(worker, "REPO", ROOT), patch.object(
            worker, "CLAUDE_EXE", sys.executable
        ), patch.object(worker.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "error_during_execution") as error:
                worker.execute(task)
        self.assertNotIn("SENSITIVE_UNRELATED_TEXT", str(error.exception))


if __name__ == "__main__":
    unittest.main()
