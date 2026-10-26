#!/usr/bin/env python3
"""P6 source-review sequencing tests, zero network or LLM usage."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
import evidence
import source_review as flow

FLOW_ID = "p6-unit-proof-001"
CLAIM = "Is OpenClaw the Planner and Hermes the Executor in this protocol?"


class PrimaryReviewWorkflowTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        (root / "docs").mkdir()
        (root / "docs/SPEC.md").write_text("OpenClaw plans.\nHermes executes.\n")
        self.capsule = evidence.capture(root, "docs/SPEC.md")
        self.outer = hashlib.sha256(self.capsule.encode()).hexdigest()
        self.original = evidence.verify(self.capsule)
        self.old = flow.STATE_DIR
        flow.STATE_DIR = root / "workflow"
        self.addCleanup(lambda: setattr(flow, "STATE_DIR", self.old))

    def fixtures(self):
        def fake_submit(key, target, capability, goal, repo_id="none",
                        parent_id=None, digest=None):
            if target in ("hermes.evidence.local", "openclaw.evidence.cloud"):
                assert parent_id == "source-001", "source parent reference lost"
                assert digest == self.outer, "result digest changed"
                assert capability == "source.verify"
            return {
                "repo.evidence.local": "source-001",
                "hermes.evidence.local": "hermes-002",
                "openclaw.evidence.cloud": "openclaw-003",
            }[target]

        def fake_wait(task_id, budget):
            if task_id == "source-001":
                return {"task": {"status": "COMPLETED"},
                        "result_text": self.capsule}
            reviewer = {
                "source": {
                    "path": "docs/SPEC.md",
                    "sha256": self.original["sha256"],
                    "size_bytes": self.original["size_bytes"]
                },
                "source_verified_before_model": True,
                "model_response": "Confirmed with [docs/SPEC.md:L1]"
            }
            return {
                "task": {"status": "COMPLETED", "run_id": "reviewer:" + task_id},
                "result_text": json.dumps(reviewer),
                "provenance": {
                    "parent_task_id": "source-001",
                    "source_sha256": self.outer
                },
            }
        return fake_submit, fake_wait

    def test_both_models_receive_one_same_sealed_source(self):
        submit, wait = self.fixtures()
        with patch.object(flow, "submit", side_effect=submit) as posted, patch.object(
            flow, "wait_receipt", side_effect=wait
        ):
            self.assertEqual(flow.run(FLOW_ID, "docs/SPEC.md", CLAIM, 15), 0)
        self.assertEqual(posted.call_count, 3)
        receipt = json.loads((flow.STATE_DIR / f"p6-{FLOW_ID}.json").read_text())
        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertEqual(receipt["source_sha256"], self.original["sha256"])
        self.assertEqual(len(receipt["reviewers"]), 2)
        self.assertTrue(all(x["evidence_verified"] for x in receipt["reviewers"]))
        self.assertEqual(
            [x["reviewer"] for x in receipt["reviewers"]],
            ["hermes_primary", "openclaw_primary"]
        )

    def test_failed_capture_stops_before_any_model_submit(self):
        def post(*args, **kwargs):
            return "source-001"
        with patch.object(flow, "submit", side_effect=post) as m, patch.object(
            flow, "wait_receipt", return_value={
                "task": {"status": "FAILED"}, "result_text": ""
            }
        ):
            with self.assertRaisesRegex(RuntimeError, "source capture failed"):
                flow.run(FLOW_ID, "docs/SPEC.md", CLAIM, 15)
        self.assertEqual(m.call_count, 1)

    def test_reject_wrong_reviewer_provenance(self):
        submit, wait = self.fixtures()
        def tampered(task_id, budget):
            x = wait(task_id, budget)
            if task_id == "hermes-002":
                x["provenance"]["source_sha256"] = "0"*64
            return x
        with patch.object(flow, "submit", side_effect=submit), patch.object(
            flow, "wait_receipt", side_effect=tampered
        ):
            with self.assertRaisesRegex(ValueError, "mismatched source provenance"):
                flow.run(FLOW_ID, "docs/SPEC.md", CLAIM, 15)

    def test_user_cannot_request_arbitrary_file(self):
        with self.assertRaises(ValueError):
            flow.run(FLOW_ID, "../other.txt", CLAIM, 15)


if __name__ == "__main__":
    unittest.main()
