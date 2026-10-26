#!/usr/bin/env python3
"""Isolated contract regression tests for the original manual agent-loop.

No local ~/.agent-loop goals, gateways, network, or live agents are touched.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
GOAL = "contract-check"


class RelayContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agent-loop-contract-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.goal = self.home / "goals" / GOAL
        self.env = {**os.environ, "AGENT_LOOP_HOME": str(self.home)}
        self.run_tool("agent-loop-init-goal", GOAL, "Isolated contract test")

    def run_tool(self, tool, *args, success=True):
        proc = subprocess.run(
            ["bash", str(BIN / tool), *map(str, args)],
            env=self.env, text=True, capture_output=True, timeout=15,
        )
        if success:
            self.assertEqual(
                proc.returncode, 0,
                f"{tool} {' '.join(map(str,args))} failed:\n{proc.stdout}\n{proc.stderr}"
            )
        else:
            self.assertNotEqual(
                proc.returncode, 0,
                f"{tool} should have rejected input: {proc.stdout}"
            )
        return proc

    def state(self):
        return json.loads((self.goal / "state.json").read_text())

    def command_text(self, n, goal=GOAL):
        return (
            "BEGIN_HERMES_COMMAND\n"
            f"goal_id: {goal}\n"
            f"iteration: {n}\n"
            "command_type: validate\n"
            "objective: Check a fixture\n"
            "instructions:\n"
            "  1. Read a harmless fixture\n"
            "validation: Check result\n"
            "report_back: HERMES_STATUS: REPORT_WRITTEN\n"
            "stop_conditions: Stop on failure\n"
            "END_HERMES_COMMAND\n"
        )

    def write_command(self, n, goal=GOAL):
        target = self.goal / "hermes-commands" / f"{n:03d}.md"
        target.write_text(self.command_text(n, goal), encoding="utf-8")
        return target

    def start_round(self, n=1):
        self.write_command(n)
        self.run_tool("agent-loop-set-state", GOAL, "COMMAND_READY")
        self.run_tool("agent-loop-relay", "--once", GOAL)
        self.assertEqual(self.state()["iteration"], n)
        self.run_tool("agent-loop-relay", "--once", GOAL, "--mark-dispatched")
        self.assertEqual(self.state()["current_state"], "DISPATCHED_TO_HERMES")

    def report_text(self, n, path, goal=GOAL):
        return (
            "BEGIN_HERMES_REPORT\n"
            f"goal_id: {goal}\n"
            f"iteration: {n}\n"
            "status: PASS\n"
            "summary: Synthetic validation complete\n"
            "changed_files: none\n"
            "commands_run:\n"
            "  - check fixture\n"
            "validation_result: PASS\n"
            "commit: none\n"
            f"report_path: {path}\n"
            "issues: none\n"
            "recommendation: proceed\n"
            "END_HERMES_REPORT\n"
        )

    def write_report(self, n=1, goal=GOAL):
        p = self.goal / "hermes-reports" / f"{n:03d}.md"
        p.write_text(self.report_text(n, p, goal), encoding="utf-8")
        return p

    def accept_report(self, n=1):
        p = self.write_report(n)
        self.run_tool("agent-loop-relay", "--once", GOAL, "--report-path", p)
        self.assertEqual(self.state()["current_state"], "HERMES_REPORT_WRITTEN")
        return p

    def decision_text(self, n, decision, approval="false", goal=GOAL):
        return (
            "BEGIN_OPENCLAW_DECISION\n"
            f"goal_id: {goal}\n"
            f"iteration: {n}\n"
            f"decision: {decision}\n"
            f"requires_human_approval: {approval}\n"
            "reason: Fixture judged\n"
            "next_expected_result: Run next command or close\n"
            "END_OPENCLAW_DECISION\n"
        )

    def write_decision(self, n=1, decision="DONE", approval="false", goal=GOAL):
        path = self.goal / "openclaw-decisions" / f"{n:03d}.md"
        path.write_text(
            self.decision_text(n, decision, approval, goal), encoding="utf-8"
        )
        return path

    def test_successful_complete_round(self):
        self.start_round(1)
        self.accept_report(1)
        self.run_tool("agent-loop-relay", "--judge-prompt", GOAL, "--mark-judging")
        p = self.write_decision(1)
        self.run_tool("agent-loop-relay", "--decision-path", GOAL, p)
        state = self.state()
        self.assertEqual(state["current_state"], "DONE")
        self.assertEqual(state["iteration"], 1)
        self.assertEqual(len(state["last_command_sha256"]), 64)
        self.assertEqual(len(state["last_report_sha256"]), 64)

    def test_reject_invalid_command_identity(self):
        self.write_command(1, "incorrect-goal")
        self.run_tool("agent-loop-set-state", GOAL, "COMMAND_READY")
        self.run_tool("agent-loop-relay", "--once", GOAL, success=False)
        self.assertEqual(self.state()["current_state"], "COMMAND_READY")
        self.assertEqual(self.state()["iteration"], 0)

    def test_reject_report_schema_identity_round_and_markers(self):
        self.start_round(1)
        path = self.write_report(1)
        valid = path.read_text()
        cases = {
            "wrong_goal": valid.replace("goal_id: contract-check", "goal_id: other"),
            "wrong_iteration": valid.replace("iteration: 1", "iteration: 2"),
            "fractional_iteration": valid.replace("iteration: 1", "iteration: 1.1"),
            "missing_required_field": valid.replace("status: PASS\n", ""),
            "wrong_status": valid.replace("status: PASS", "status: GOOD"),
            "wrong_declared_path": valid.replace(
                f"report_path: {path}", "report_path: /tmp/other.md"
            ),
            "duplicate_marker": valid + "BEGIN_HERMES_REPORT\n",
            "duplicate_key": valid.replace(
                "status: PASS", "status: PASS\nstatus: FAIL"
            ),
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                path.write_text(text)
                self.run_tool(
                    "agent-loop-relay", "--once", GOAL,
                    "--report-path", path, success=False
                )
                self.assertEqual(
                    self.state()["current_state"], "DISPATCHED_TO_HERMES"
                )
                self.assertIsNone(self.state()["last_report"])

    def test_report_cannot_change_silently_after_ingest(self):
        self.start_round()
        path = self.accept_report()
        path.write_text(path.read_text().replace(
            "summary: Synthetic", "summary: Modified"
        ))
        self.run_tool("agent-loop-relay", "--judge-prompt", GOAL, success=False)
        self.assertEqual(self.state()["current_state"], "HERMES_REPORT_WRITTEN")

    def test_reject_judging_result_if_report_changed(self):
        self.start_round()
        path = self.accept_report()
        self.run_tool("agent-loop-relay", "--judge-prompt", GOAL, "--mark-judging")
        path.write_text(path.read_text().replace(
            "recommendation: proceed", "recommendation: changed"
        ))
        decision = self.write_decision()
        self.run_tool(
            "agent-loop-relay", "--decision-path", GOAL, decision, success=False
        )
        self.assertEqual(self.state()["current_state"], "OPENCLAW_JUDGING")

    def test_command_cannot_change_silently_after_preview(self):
        path = self.write_command(1)
        self.run_tool("agent-loop-set-state", GOAL, "COMMAND_READY")
        self.run_tool("agent-loop-relay", "--once", GOAL)
        path.write_text(path.read_text().replace(
            "objective: Check", "objective: Changed"
        ))
        self.run_tool(
            "agent-loop-relay", "--once", GOAL, "--mark-dispatched", success=False
        )
        self.assertEqual(self.state()["current_state"], "COMMAND_READY")

    def test_reject_bad_decision_identity_round_boolean_and_markers(self):
        self.start_round()
        self.accept_report()
        self.run_tool("agent-loop-relay", "--judge-prompt", GOAL, "--mark-judging")
        path = self.write_decision()
        valid = path.read_text()
        cases = {
            "wrong_goal": valid.replace(
                "goal_id: contract-check", "goal_id: unrelated"
            ),
            "wrong_iteration": valid.replace("iteration: 1", "iteration: 2"),
            "fractional_iteration": valid.replace("iteration: 1", "iteration: 1.2"),
            "bad_approval": valid.replace(
                "requires_human_approval: false",
                "requires_human_approval: yes"
            ),
            "missing_field": valid.replace("reason: Fixture judged\n", ""),
            "missing_marker": valid.replace("END_OPENCLAW_DECISION\n", ""),
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                path.write_text(text)
                self.run_tool(
                    "agent-loop-relay", "--decision-path", GOAL, path,
                    success=False
                )
                self.assertEqual(
                    self.state()["current_state"], "OPENCLAW_JUDGING"
                )
                self.assertIsNone(self.state()["last_decision"])

    def test_next_round_and_human_confirmation(self):
        self.start_round(1)
        self.accept_report(1)
        self.run_tool("agent-loop-relay", "--judge-prompt", GOAL, "--mark-judging")
        decision = self.write_decision(1, "NEXT_COMMAND", "true")
        self.run_tool("agent-loop-relay", "--decision-path", GOAL, decision)
        self.assertEqual(self.state()["current_state"], "OPENCLAW_PLANNING")
        self.assertTrue(self.state()["human_approval_required"])
        self.assertIsNone(self.state()["human_approved"])

        self.write_command(2)
        self.run_tool("agent-loop-set-state", GOAL, "COMMAND_READY")
        self.run_tool("agent-loop-relay", "--once", GOAL)
        self.assertEqual(self.state()["current_state"], "WAITING_HUMAN_APPROVAL")
        self.assertEqual(self.state()["iteration"], 2)
        self.run_tool("agent-loop-relay", "--once", GOAL, "--mark-dispatched")
        self.assertTrue(self.state()["human_approved"])
        self.accept_report(2)

    def test_command_order_is_numeric(self):
        self.write_command(9)
        self.write_command(10)
        self.run_tool("agent-loop-set-state", GOAL, "COMMAND_READY")
        self.run_tool("agent-loop-relay", "--once", GOAL)
        self.assertEqual(self.state()["iteration"], 10)

    def test_read_only_json_status_for_an_agent_adapter(self):
        before = (self.goal / "state.json").read_bytes()
        proc = subprocess.run(
            ["python3", str(BIN / "agent-loop-status-json"), "--goal", GOAL],
            env=self.env, capture_output=True, text=True, timeout=15
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snapshot = json.loads(proc.stdout)
        self.assertEqual(snapshot["schema"], "agent-loop.status/1")
        self.assertFalse(snapshot["remote_artifacts_fetchable"])
        self.assertEqual(snapshot["total_goals"], 1)
        self.assertEqual(snapshot["goals"][0]["current_state"], "INIT")
        self.assertEqual(before, (self.goal / "state.json").read_bytes())

        proc = subprocess.run(
            ["python3", str(BIN / "agent-loop-status-json"), "--all"],
            env=self.env, capture_output=True, text=True, timeout=15
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["total_goals"], 1)

    def test_installer_in_existing_data_home(self):
        existing = self.goal / "state.json"
        before = existing.read_bytes()
        proc = subprocess.run(
            ["bash", str(ROOT / "scripts/install.sh")],
            env=self.env, capture_output=True, text=True, timeout=15
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.home / "bin/agent-loop-status-json").is_file())
        self.assertEqual(before, existing.read_bytes())

    def test_reject_invalid_goal_paths_and_incompatible_flags(self):
        for tool, args in (
            ("agent-loop-relay", ("--once", "../contract-check")),
            ("agent-loop-show", ("../contract-check",)),
            ("agent-loop-set-state", ("../contract-check", "DONE")),
            ("agent-loop-relay", ("--once", GOAL, "--mark-judging")),
        ):
            with self.subTest(tool=tool, args=args):
                proc = self.run_tool(tool, *args, success=False)
                self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
