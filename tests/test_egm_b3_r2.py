#!/usr/bin/env python3
"""Tests for real-source, unplanted EGM B3-R2 packet and blinded scoring."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"benchmarks/egm_b3_r2"
def load(name):
    p=BASE/(name+".py")
    spec=importlib.util.spec_from_file_location("test_b3r2_"+name,p)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

builder=load("build_packets")
runner=load("run_cloud")
blind=load("prepare_blind")
score=load("score_delivery")

class SourceIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.m=json.loads((BASE/"manifest.json").read_text(encoding="utf-8"))

    def test_three_source_derived_cases_no_planted_ground_truth(self):
        self.assertIs(self.m["planted_defects"],False)
        self.assertEqual(len(self.m["cases"]),3)
        self.assertFalse((BASE/"ground_truth.json").exists())

    def test_every_packet_line_is_from_frozen_git(self):
        from collections import Counter
        for case in self.m["cases"]:
            text=(ROOT/case["packet_path"]).read_text(encoding="utf-8")
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),case["packet_sha256"])
            found={}
            for source in case["segments"]:
                body=subprocess.check_output(
                    ["git","show",f"{self.m['revision']}:{source['path']}"],
                    cwd=ROOT).decode()
                self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),source["original_source_sha256"])
                lines=body.splitlines()
                for i in range(source["start"],source["end"]+1):
                    label=f"[{source['path']}:L{i}] {lines[i-1]}"
                    found[label]=found.get(label,0)+1
                    self.assertIn(label,text)
            self.assertTrue(all(n==1 for n in found.values()))

    def test_balanced_twelve_invocations(self):
        jobs=runner.build_schedule(self.m)
        self.assertEqual(len(jobs),12)
        for case in self.m["cases"]:
            subset=[x for x in jobs if x["case"]==case["case_id"]]
            self.assertEqual(sum(x["arm"]=="baseline" for x in subset),2)
            self.assertEqual(sum(x["arm"]=="goldfish" for x in subset),2)
            self.assertEqual({x["repeat"] for x in subset},{1,2})
            self.assertNotEqual(subset[0]["arm"],subset[2]["arm"])

    def test_compact_source_packets_are_not_modified(self):
        compact=json.loads((BASE/"manifest_compact.json").read_text())
        self.assertIs(compact["planted_defects"],False)
        self.assertEqual(compact["revision"],self.m["revision"])
        self.assertEqual(len(compact["cases"]),3)
        for case in compact["cases"]:
            packet=(ROOT/case["packet_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(packet).hexdigest(),case["packet_sha256"])
            for src in case["segments"]:
                blob=subprocess.check_output(["git","show",f"{compact['revision']}:{src['path']}"],cwd=ROOT)
                self.assertEqual(hashlib.sha256(blob).hexdigest(),src["original_source_sha256"])

    def test_incomplete_runs_are_not_reported_as_model_findings(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            metrics=score.metrics(BASE,"compact_adaptive",root)
            self.assertEqual(metrics["arm_summary"]["baseline"]["completed"],0)
            self.assertEqual(metrics["arm_summary"]["goldfish"]["completed"],0)
            self.assertEqual(sum(x["both_delivered"] for x in metrics["pairs"]),0)
            self.assertEqual(metrics["findings_quality_status"],"REQUIRES_BLINDED_EVIDENCE_ADJUDICATION")

    def test_json_output_parser(self):
        self.assertEqual(runner.unpack('{"findings":[],"summary":"ok"}')["findings"],[])
        self.assertIsNone(runner.unpack("This is not JSON."))

    def test_blind_reviewer_prompt_has_no_arm_or_repeat_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            result_dir=root/"results"; result_dir.mkdir()
            case=self.m["cases"][0]
            payload={"case":case["case_id"],"arm":"goldfish","repeat":1,
                     "status":"COMPLETED","packet_sha256":case["packet_sha256"],
                     "findings":[{"issue":"state transition unclear","why":"ambiguous",
                                  "severity":"Major","fix":"specify",
                                  "source_refs":[f"{case['segments'][0]['path']}:L{case['segments'][0]['start']}"]}]}
            (result_dir/f"{case['case_id']}_r1_goldfish.json").write_text(json.dumps(payload))
            out=root/"blind"
            blind.prepare(BASE,result_dir,out)
            prompt=(out/f"{case['case_id']}.judge_prompt.txt").read_text()
            self.assertNotIn('"arm"',prompt)
            self.assertNotIn('"repeat"',prompt)
            self.assertIn('"blind_id"',prompt)
            mapping=json.loads((out/"mapping.private.json").read_text())
            self.assertTrue(any("goldfish" in value for value in mapping.values()))

if __name__=="__main__":
    unittest.main()
