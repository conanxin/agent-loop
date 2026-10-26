#!/usr/bin/env python3
"""P6 evidence allowlist, integrity, two-reviewer protocol. No live model calls."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
import evidence
import worker


class SourceCapsuleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cxpan-evidence-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "docs").mkdir()
        self.spec_path = self.repo / "docs/SPEC.md"
        self.text = "Original purpose.\r\nOpenClaw plans.\nHermes executes.\n"
        self.spec_path.write_bytes(self.text.encode("utf-8"))

    def test_exact_original_utf8_and_two_hashes(self):
        raw = evidence.capture(self.repo, "docs/SPEC.md")
        obj = evidence.verify(raw, hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(obj["text"], self.text)
        self.assertEqual(obj["size_bytes"], len(self.text.encode()))
        self.assertEqual(obj["line_count"], 3)
        self.assertEqual(obj["sha256"], hashlib.sha256(self.text.encode()).hexdigest())
        view = evidence.primary_excerpt(obj)
        self.assertIn("[docs/SPEC.md:L2] OpenClaw plans.", view)

    def test_tampering_and_noncanonical_inputs_are_rejected(self):
        raw = evidence.capture(self.repo, "docs/SPEC.md")
        original_outer_sha = hashlib.sha256(raw.encode()).hexdigest()
        bad = raw.replace("Hermes executes.", "Hermes abstains.")
        with self.assertRaisesRegex(ValueError, "task result SHA"):
            evidence.verify(bad, original_outer_sha)
        with self.assertRaisesRegex(ValueError, "source content SHA"):
            evidence.verify(bad)
        with self.assertRaises(ValueError):
            evidence.verify('{"schema":"unknown"}')

    def test_disallow_nonallowlisted_symlinks_and_large_files(self):
        for name in ("../secrets", "D:/Downloads/secret", "/etc/passwd",
                     "docs/UNKNOWN.md"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                evidence.capture(self.repo, name)
        self.spec_path.unlink()
        external = self.repo / "elsewhere.txt"
        external.write_text("not approved")
        self.spec_path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "symlink"):
            evidence.capture(self.repo, "docs/SPEC.md")
        self.spec_path.unlink()
        self.spec_path.write_text("M" * (evidence.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "quota"):
            evidence.capture(self.repo, "docs/SPEC.md")


class SourceReviewWorkerTest(unittest.TestCase):
    def test_local_worker_refuses_mismatch_and_passes_line_provenance(self):
        text = "Verified original.\nPlanner is OpenClaw.\nHermes executes."
        capsule = json.dumps({
            "schema": evidence.SCHEMA, "repo_id": "agent-loop",
            "path": "docs/SPEC.md",
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "size_bytes": len(text.encode()),
            "line_count": 3, "text": text
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        outer = hashlib.sha256(capsule.encode()).hexdigest()
        task = {
            "task_id": "child-review", "project_id": "CX-PAN",
            "goal": "Confirm the actor responsibilities",
        }

        def query(method, path, payload=None):
            if path.endswith("child-review"):
                return {"provenance": {"parent_task_id": "evidence-parent",
                                       "source_sha256": outer}}
            return {"task": {"status": "COMPLETED",
                             "target": "repo.evidence.local",
                             "project_id": "CX-PAN"},
                    "result_text": capsule}
        with patch.object(worker, "request_json", side_effect=query), patch.object(
            worker, "hermes_review", return_value=("Confirmed with lines", "run-123")
        ) as model:
            result, run_id = worker.hermes_evidence_review(task)
        self.assertEqual(run_id, "run-123")
        body = json.loads(result)
        self.assertTrue(body["source_verified_before_model"])
        self.assertEqual(body["source"]["sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertIn("[docs/SPEC.md:L2]", model.call_args.args[0])

        def tampered(method, path, payload=None):
            value = query(method, path, payload)
            if "result_text" in value:
                value["result_text"] = value["result_text"].replace("Hermes executes.", "Hermes deletes.")
            return value
        with patch.object(worker, "request_json", side_effect=tampered):
            with self.assertRaisesRegex(ValueError, "task result SHA"):
                worker.hermes_evidence_review(task)


if __name__ == "__main__":
    unittest.main()
