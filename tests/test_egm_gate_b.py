#!/usr/bin/env python3
"""Offline contract checks for EGM Gate-B A/B probes. Never invokes models."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
import egm_cloud_context_ab as cloud
import egm_isolation_ab as hermes
import egm_local_probe as strict
import evidence


class GateBIsolationToolingTest(unittest.TestCase):

    def test_hermes_chat_goldfish_always_sets_ignore_rules_without_resume(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            prompt = folder / "query.txt"
            prompt.write_text("SOURCE_WORD=blue-otter-harbor")
            completed = subprocess.CompletedProcess(
                [], 0, "SOURCE_WORD=blue-otter-harbor\nAMBIENT_WORD=NONE\n",
                "session_id: local-a1b2c3d4\n")
            with patch.object(hermes.subprocess, "run", return_value=completed) as mock_run:
                row = hermes.run_one("goldfish", folder, prompt, True, 60)
            command = mock_run.call_args.args[0]
            self.assertEqual(command[0], str(hermes.HERMES))
            self.assertIn("--ignore-rules", command)
            self.assertEqual(command[command.index("--source")+1], "tool")
            self.assertEqual(command[command.index("--in")+1], str(folder))
            self.assertNotIn("--resume", command)
            self.assertNotIn("-z", command)
            self.assertIn("--query-file", command)
            self.assertEqual(row["status"], "COMPLETED")

    def test_hermes_control_mode_does_not_fake_isolation_flag(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            prompt = folder / "query.txt"
            prompt.write_text("test")
            result = subprocess.CompletedProcess([], 0, "control", "")
            with patch.object(hermes.subprocess, "run", return_value=result) as mock_run:
                hermes.run_one("control", folder, prompt, False, 60)
            self.assertNotIn("--ignore-rules", mock_run.call_args.args[0])

    def test_cloud_control_only_changes_context_injection_not_tool_policy(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pinned_dir = root / ".openclaw"
            pinned_dir.mkdir()
            pinned = pinned_dir / "cxpan-p5-readonly.json5"
            original = ('{"$include": "./openclaw.json", "tools": {"deny": ["*"]},'
                        ' "agents": {"defaults": {"contextInjection": "never"}}}')
            pinned.write_text(original, encoding="utf-8")
            with patch.object(cloud, "PINNED", pinned), patch.object(cloud, "HOME", root):
                folder = root / "scratch"
                a, s, p, control = cloud.prepare(folder)
                rendered = control.read_text(encoding="utf-8")
                self.assertIn('"contextInjection": "always"', rendered)
                self.assertIn('"deny": ["*"]', rendered)
                self.assertIn('"$include": "./openclaw.json"', rendered)
                self.assertEqual(pinned.read_text(encoding="utf-8"), original)
                self.assertEqual(control.parent, pinned_dir)
                self.assertNotEqual(a, s)
                control.unlink(missing_ok=True)

    def test_cloud_headless_runs_pinned_json_with_explicit_cwd(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            prompt = folder / "query.txt"
            prompt.write_text("SOURCE_WORD=violet-otter-birch")
            config = folder / "test.json5"
            config.write_text("{}")
            data = {"ok": True, "status": "ok",
                    "final": "SOURCE_WORD=violet-otter-birch\nAMBIENT_WORD=NONE",
                    "sessionId": "distinct-run", "toolSummary": {"calls": 0}}
            p = subprocess.CompletedProcess([], 0, json.dumps(data), "")
            with patch.object(cloud.subprocess, "run", return_value=p) as run:
                out = cloud.run_one("goldfish", config, folder, prompt,
                                    "hidden-private-word", "violet-otter-birch", 95)
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[cmd.index("--config")+1], str(config))
            self.assertEqual(cmd[cmd.index("--cwd")+1], str(folder))
            self.assertIn("--json", cmd)
            self.assertNotIn("--isolated", cmd)
            self.assertNotIn("--resume", cmd)
            self.assertEqual(out["tool_calls"], 0)
            self.assertTrue(out["explicit_source_marker_seen_in_answer"])
            self.assertFalse(out["ambient_marker_seen_in_answer"])


class StrictGoldfishProbeTest(unittest.TestCase):

    def test_full_primary_source_runs_through_strict_chat_flags(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            body = "Spec introduction.\nTest plan.\n"
            capsule = json.dumps({
                "schema": evidence.SCHEMA,
                "repo_id": "agent-loop",
                "path": "docs/SPEC.md",
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "size_bytes": len(body.encode()),
                "line_count": 2,
                "text": body
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            source = {"task": {"status": "COMPLETED", "target": "repo.evidence.local"},
                      "result_text": capsule}
            cp = subprocess.CompletedProcess(
                [], 0, "Document needs a test [docs/SPEC.md:L2]",
                "session_id: local-a1b2c3d4\n")
            with patch.object(strict, "request_json", return_value=source), patch.object(
                strict, "HERMES", Path("/bin/true")
            ), patch.object(strict.subprocess, "run", return_value=cp) as call:
                rc = strict.run("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                                "egm-b-unit-123", 80, folder)
            cmd = call.call_args.args[0]
            self.assertEqual(rc, 0)
            self.assertIn("--ignore-rules", cmd)
            self.assertIn("--source", cmd)
            self.assertNotIn("-z", cmd)
            self.assertNotIn("--resume", cmd)
            receipt = json.loads((folder/"egm-b-unit-123.json").read_text())
            self.assertEqual(receipt["hermes_session_id"], "local-a1b2c3d4")
            self.assertEqual(receipt["check"]["explicit_path_line_citations"], 1)


if __name__ == "__main__":
    unittest.main()
