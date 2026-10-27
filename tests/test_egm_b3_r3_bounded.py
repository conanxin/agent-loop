#!/usr/bin/env python3
"""Offline tests for B3-R3 model preflight and bounded real-source review."""
from pathlib import Path
import importlib.util
import json
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
SOURCES=BASE/"benchmarks/egm_b3_r2"
SPEC=importlib.util.spec_from_file_location("egm_b3r3_bounded",BASE/"benchmarks/egm_b3_r3/bounded_review.py")
review=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class BoundedReviewerTests(unittest.TestCase):
    def test_zero_findings_json_is_valid(self):
        self.assertEqual(review.parse_review('{"findings":[],"summary":"none"}',""),[])

    def test_real_reference_validation_does_not_prove_semantics(self):
        packet=(SOURCES/"compact_packets/p9-public-mcp-boundary.txt").read_text(encoding="utf-8")
        ref="bridge/mcp_gateway.py:L248"
        self.assertIn("["+ref+"]",packet)
        answer=json.dumps({"findings":[{
            "severity":"Major","issue":"candidate","source_refs":[ref,"bridge/mcp_gateway.py:L999"],
            "why":"needs verification"
        }]})
        findings=review.parse_review(answer,packet)
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0]["structurally_valid_refs"],[ref])
        self.assertEqual(len(findings[0]["source_refs"]),2)

    def test_invalid_schema_is_not_forgiven(self):
        self.assertIsNone(review.parse_review("not JSON",""))
        self.assertIsNone(review.parse_review('{"findings":[{"issue":"bad","source_refs":"text"}]}',""))
        self.assertIsNone(review.parse_review('{"findings":[{"issue":"a","source_refs":[]},'
                                             '{"issue":"b","source_refs":[]},'
                                             '{"issue":"c","source_refs":[]}]}',""))

    def test_duplicate_workflow_does_not_submit_again(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            p=home/"egm-b3r3-existing-id"
            p.mkdir()
            (p/"receipt.json").write_text(json.dumps({"status":"COMPLETED"}))
            with patch.object(review,"BASE",home),patch.object(
                review.subprocess,"run"
            ) as model:
                review.run("egm-b3r3-existing-id",SOURCES,"p9-public-mcp-boundary",70)
            model.assert_not_called()

    def test_partial_workflow_requires_inspection_not_paid_retry(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            p=home/"egm-b3r3-incomplete-id"
            p.mkdir()
            (p/"prompt.txt").write_text("previous request may still be running")
            with patch.object(review,"BASE",home),patch.object(
                review.subprocess,"run"
            ) as model:
                with self.assertRaisesRegex(RuntimeError,"previous incomplete"):
                    review.run("egm-b3r3-incomplete-id",SOURCES,"p6-evidence-integrity",70)
            model.assert_not_called()

    def test_trajectory_distinguishes_submitted_and_model_completed(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"trace.sqlite"
            conn=sqlite3.connect(db)
            conn.execute("CREATE TABLE trajectory_runtime_events(seq INT,event_json TEXT)")
            for i,event in enumerate([
                {"type":"session.started","modelId":"MiniMax-M2.7"},
                {"type":"context.compiled","data":{"tools":[]}},
                {"type":"prompt.submitted"},
                {"type":"model.completed"},
                {"type":"trace.artifacts","data":{"usage":{"total":222,"input":150,"output":50}}}
            ]):
                conn.execute("INSERT INTO trajectory_runtime_events VALUES(?,?)",
                             (i,json.dumps(event)))
            conn.commit();conn.close()
            r=review.trace_events(db)
            self.assertTrue(r["prompt_submitted"])
            self.assertTrue(r["model_completed"])
            self.assertEqual(r["tool_calls"],0)
            self.assertEqual(r["model_visible_tools"],0)
            self.assertEqual(r["model_id"],"MiniMax-M2.7")
            self.assertEqual(r["tokens"]["total"],222)


if __name__=="__main__":
    unittest.main()
