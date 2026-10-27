#!/usr/bin/env python3
"""Validate the committed, sanitized B3-R3 reliability-stage results.

No cloud/model calls and no secret material from private run directories.
"""
from pathlib import Path
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"benchmarks/egm_b3_r3"


class B3R3ResultsIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results=json.loads((DATA/"results_summary.json").read_text(encoding="utf-8"))
        cls.invariants=json.loads((DATA/"invariants_summary.json").read_text(encoding="utf-8"))

    def test_matched_p6_input_and_distinct_model_outcomes(self):
        r=self.results
        p6=r["experiments"]["p6_m27_smoke"]
        flash=r["experiments"]["p6_flash_same_prompt"]
        self.assertTrue(r["paired_same_prompt_control"]["input_identical"])
        self.assertEqual(p6["prompt_sha256"],flash["prompt_sha256"])
        self.assertEqual(p6["source_sha256"],flash["source_sha256"])
        self.assertEqual(p6["status"],"COMPLETED")
        self.assertEqual(flash["status"],"TIMEOUT_NO_MODEL_COMPLETE")
        self.assertEqual(p6["requested_thinking"],"medium")
        self.assertEqual(flash["requested_thinking"],"adaptive")

    def test_bounded_review_traces_and_no_tool_calls(self):
        r=self.results
        success=[r["experiments"][n] for n in (
            "p6_m27_smoke","p9_m27_smoke","p6_m27_review","p9_m27_review")]
        self.assertEqual(len(success),4)
        self.assertEqual(len({x["session_id"] for x in success}),4)
        self.assertTrue(all(x["session_id"] for x in success))
        for x in success:
            self.assertEqual(x["status"],"COMPLETED")
            self.assertTrue(x["model_completed"])
            self.assertEqual(x["actual_model"],"MiniMax-M2.7")
            self.assertEqual(x["model_visible_tools"],0)
            self.assertEqual(x["tool_calls"],0)
            self.assertIsInstance(x["total_tokens"],int)
        self.assertEqual(r["bounded_review_m27_medium"]["completed"],2)
        self.assertEqual(r["smoke_m27_medium"]["completed"],2)

    def test_invariants_reproduced_in_temporary_data_only(self):
        r=self.invariants
        self.assertTrue(r["no_production_file_or_database_mutation"])
        self.assertTrue(r["evidence_capsule"]["verification_rejected"])
        self.assertGreater(r["evidence_capsule"]["json_capsule_bytes"],40000)
        self.assertTrue(r["safe_quota"]["same_key_retried_without_second_slot"])
        self.assertEqual(r["safe_quota"]["reserved_rows_after_failure"],1)
        self.assertEqual(r["safe_quota"]["reserved_rows_after_second_unique_key"],2)

if __name__=="__main__":
    unittest.main()
