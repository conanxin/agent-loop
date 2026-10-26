#!/usr/bin/env python3
"""P5 cloud OpenClaw worker and review-chain contract tests; no model calls."""
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))


def module(filename, module_name):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "bridge" / filename)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


cloud = module("cloud_worker.py", "p5_cloud_worker")
chain = module("review_chain.py", "p5_review_chain")
PARENT = "d00acdaa-4595-4655-86dc-0550a336e8a5"


class CloudWorkerTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.exe = self.root / "openclaw"
        self.exe.write_text("")
        self.config = self.root / "readonly.json5"
        self.config.write_text('{"tools": {"deny": ["*"]}}')
        self.old = (cloud.OPENCLAW_CLI, cloud.OPENCLAW_CONFIG, cloud.WORKDIR)
        cloud.OPENCLAW_CLI, cloud.OPENCLAW_CONFIG, cloud.WORKDIR = (
            self.exe, self.config, self.root
        )
        self.addCleanup(self.restore)

    def restore(self):
        cloud.OPENCLAW_CLI, cloud.OPENCLAW_CONFIG, cloud.WORKDIR = self.old

    def test_model_response_and_native_session_id(self):
        output = {
            "ok": True, "status": "ok", "final": "OpenClaw independent review",
            "sessionId": "native-openclaw-uuid", "toolSummary": {"calls": 0},
        }
        proc = CompletedProcess([], returncode=0, stdout=json.dumps(output), stderr="")
        with patch.object(cloud.subprocess, "run", return_value=proc) as runner:
            result, run_id = cloud.review("This is a harmless source report")
        self.assertIn("independent review", result)
        self.assertEqual(run_id, "openclaw:native-openclaw-uuid")
        cmd = runner.call_args.args[0]
        self.assertIn("--config", cmd)
        self.assertIn("--thinking", cmd)
        self.assertEqual(cmd[cmd.index("--thinking") + 1], "adaptive")
        self.assertNotIn("--deliver", cmd)
        self.assertFalse(runner.call_args.kwargs.get("shell", False))

    def test_reject_tool_invocation(self):
        output = {
            "ok": True, "status": "ok", "final": "hello",
            "toolSummary": {"calls": 1}
        }
        proc = CompletedProcess([], returncode=0, stdout=json.dumps(output), stderr="")
        with patch.object(cloud.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "unexpectedly invoked"):
                cloud.review("This is a harmless source report")

    def test_reject_unsafe_pin(self):
        self.config.write_text('{"tools":{"allow":["exec"]}}')
        with self.assertRaisesRegex(RuntimeError, "deny all tools"):
            cloud.review("This is a harmless source report")

    def test_reject_nonzero_without_raw_output(self):
        proc = CompletedProcess([], returncode=1,
                                stdout="DO_NOT_LEAK_PRIVATE_RESULT",
                                stderr="DO_NOT_LEAK_ERROR")
        with patch.object(cloud.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "exited 1") as err:
                cloud.review("This is a harmless source report")
        self.assertNotIn("DO_NOT_LEAK", str(err.exception))


class ReviewChainTest(unittest.TestCase):
    def test_openclaw_hop_provenance_matches_hermes(self):
        requests = []
        answer = "Hermes review: " + "This claim needs verification. " * 20

        def fake_request(method, path, data=None):
            requests.append((method, path, data))
            if method == "GET":
                return {
                    "task": {
                        "task_id": PARENT, "target": "hermes.model.local",
                        "status": "COMPLETED", "run_id": "hermes-oneshot:p4",
                        "project_id": "CX-PAN",
                    },
                    "result_text": answer,
                }
            return {"task": {"task_id": "openclaw-review"}, "duplicate": False}

        with patch.object(chain, "request_json", side_effect=fake_request):
            created = chain.create_openclaw_review(PARENT)
        self.assertFalse(created["duplicate"])
        self.assertEqual(requests[0][0], "GET")
        posted = requests[1][2]
        self.assertEqual(posted["parent_task_id"], PARENT)
        self.assertEqual(posted["target"], "openclaw.model.cloud")
        self.assertEqual(posted["capability"], "text.review")
        self.assertEqual(
            posted["source_sha256"],
            hashlib.sha256(answer.encode("utf-8")).hexdigest()
        )
        self.assertTrue(len(posted["goal"]) <= 3000)
        self.assertIn(answer[:100], posted["goal"])

    def test_reject_failed_source(self):
        def fail_request(*args, **kwargs):
            return {
                "task": {
                    "status": "FAILED", "target": "hermes.model.local",
                    "project_id": "CX-PAN"
                },
                "result_text": "not valid"
            }
        with patch.object(chain, "request_json", side_effect=fail_request):
            with self.assertRaisesRegex(ValueError, "completed Hermes"):
                chain.create_openclaw_review(PARENT)


if __name__ == "__main__":
    unittest.main()
