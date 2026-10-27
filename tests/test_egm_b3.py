#!/usr/bin/env python3
"""Offline invariants of the three-fixture EGM B3 paired design-review pilot."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"benchmarks/egm_b3"
spec=importlib.util.spec_from_file_location("b3_score",BASE/"score.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
spec2=importlib.util.spec_from_file_location("b3_pilot_score",BASE/"score_pilot.py")
mod2=importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mod2)

class SeededExperimentTest(unittest.TestCase):
    def setUp(self):
        self.truth=json.loads((BASE/"ground_truth.json").read_text())
        self.manifest=json.loads((BASE/"manifest.json").read_text())

    def test_three_real_source_derived_documents_and_six_faults(self):
        self.assertEqual(len(self.truth["cases"]),3)
        self.assertEqual(len({c["source_file"] for c in self.truth["cases"]}),3)
        self.assertEqual(sum(len(c["seeded_faults"]) for c in self.truth["cases"]),6)
        for c in self.truth["cases"]:
            source=ROOT/c["source_file"]
            original=subprocess.check_output(
                ["git","show", f"{self.manifest['source_git_commit']}:{c['source_file']}"],
                cwd=ROOT)
            current=hashlib.sha256(original).hexdigest()
            self.assertEqual(current,c["source_sha256"])
            p=BASE/"fixtures"/(c["id"]+".md")
            body=p.read_text(encoding="utf-8")
            self.assertEqual(hashlib.sha256(body.encode("utf-8")).hexdigest(),c["fixture_sha256"])
            lines=body.splitlines()
            for f in c["seeded_faults"]:
                self.assertEqual(lines[f["line"]-1],"- "+f["exact_seeded_claim"])
            self.assertIn(c["valid_decoy"],body)

    def test_scoring_does_not_call_any_models(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            c=self.truth["cases"][0]
            case=c["id"]
            for arm in ("baseline","goldfish"):
                payload={"fixture_sha256":c["fixture_sha256"],"status":"COMPLETED",
                         "seconds":2,"findings":[{"line":c["seeded_faults"][0]["line"],
                           "issue":"contradicts the transition table","evidence":"",
                           "severity":"Major"}],
                         "trace":{"usage_tokens":{"input":20,"output":7,"total":27},
                                  "tool_call_events":0,"tool_schema_count":0}}
                (root/f"{case}_{arm}.json").write_text(json.dumps(payload))
            out=mod.score(root)
            hits=[c["provisional_seeded_hits"] for c in out["cases"]
                  if c["case"]==case]
            self.assertEqual(hits,[1,1])
            self.assertTrue(out["provisional_only"])
            self.assertFalse(out["blind_human_graded"])

    def test_score_pilot_uses_both_issue_and_evidence_anchors(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            c=self.truth["cases"][0]
            src_sha=c["fixture_sha256"]
            for arm in ("baseline","goldfish"):
                d={"case":c["id"],"arm":arm,"source_sha256":src_sha,
                   "status":"COMPLETED","elapsed_seconds":12.5,
                   "findings":[
                    {"line":c["seeded_faults"][0]["line"],"issue":"conflict","evidence":"L12"},
                    {"line":12,"issue":"conflict with repair mapping","evidence":"L"+str(c["seeded_faults"][1]["line"])}],
                   "trace_meta":{"usage_tokens":{"total":100},"tool_call_events":0,
                                 "tool_schema_count":0}}
                (root/(c["id"]+"_"+arm+".json")).write_text(json.dumps(d))
            score=mod2.evaluate(root)
            self.assertEqual(score["complete_pairs"],1)
            self.assertEqual(score["pairs"][0]["baseline_provisional_hits"],2)
            self.assertEqual(score["pairs"][0]["goldfish_provisional_hits"],2)
            self.assertTrue(score["manual_semantic_adjudication_required"])

    def test_ground_truth_not_a_model_input(self):
        runner=(BASE/"run_cloud.py").read_text(encoding="utf-8")
        self.assertNotIn('ground_truth.json").read_text',runner)
        self.assertIn("manifest.json",runner)
        self.assertIn('"toolSearch": false',runner)
        self.assertIn('if directory.exists() and any(directory.iterdir())',runner)


if __name__=="__main__":unittest.main()
