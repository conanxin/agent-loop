#!/usr/bin/env python3
"""Offline EGM-R2 protocol and isolation-label unit checks, no model calls."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
import egm_local_probe as probe


class EgmLocalProbeTest(unittest.TestCase):
    def setUp(self):
        self.source_text = "第一行：目标。\n第二行：测试。\n"
        self.capsule = {
            "schema": "cxpan.evidence/1",
            "repo_id": "agent-loop",
            "path": "docs/SPEC.md",
            "sha256": hashlib.sha256(self.source_text.encode("utf-8")).hexdigest(),
            "size_bytes": len(self.source_text.encode("utf-8")),
            "line_count": 2,
            "text": self.source_text,
        }

    def test_prompt_contains_all_lines_but_no_external_history(self):
        prompt = probe.build_prompt(self.capsule)
        self.assertIn("[docs/SPEC.md:L1] 第一行：目标。", prompt)
        self.assertIn("[docs/SPEC.md:L2] 第二行：测试。", prompt)
        self.assertIn(self.capsule["sha256"], prompt)
        self.assertIn("不读取会话历史", prompt)
        self.assertNotIn("CONTEXT_FROM_ELEPHANT", prompt)

    def test_model_citations_are_structural_not_semantic_proof(self):
        outcome = probe.analyze_result(
            self.capsule,
            "一条建议：请说明如何测试。[docs/SPEC.md:L2]",
        )
        self.assertEqual(outcome["explicit_path_line_citations"], 1)
        self.assertTrue(outcome["source_integrity_verified"])
        self.assertFalse(outcome["model_semantic_accuracy_verified"])
        self.assertFalse(outcome["session_history_isolation_verified"])

    def test_rejects_untraceable_citations(self):
        with self.assertRaisesRegex(ValueError, "citation"):
            probe.analyze_result(self.capsule, "没有任何原文引用")
        with self.assertRaisesRegex(ValueError, "outside"):
            probe.analyze_result(self.capsule, "越界 [docs/SPEC.md:L99]")

    def test_same_workflow_id_reuses_completed_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "egm-r2-probe.json"
            path.write_text(json.dumps({
                "source_task_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "status": "COMPLETED",
            }), encoding="utf-8")
            with patch.object(probe, "request_json") as network, patch.object(
                probe.subprocess, "run"
            ) as subprocess_call:
                code = probe.run("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                                 "egm-r2-probe", 60, output_dir=Path(td))
            self.assertEqual(code, 0)
            network.assert_not_called()
            subprocess_call.assert_not_called()

    def test_same_workflow_id_cannot_retarget_another_source(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "egm-r2-probe.json").write_text(json.dumps({
                "source_task_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "status": "COMPLETED",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "another source"):
                probe.run("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                          "egm-r2-probe", 60, output_dir=Path(td))


if __name__ == "__main__":
    unittest.main()
