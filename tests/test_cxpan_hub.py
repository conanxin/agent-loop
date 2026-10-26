#!/usr/bin/env python3
"""Cloud queue contract and HTTP regression tests, all using temporary files."""
import importlib.util
import hashlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "bridge/hub.py"
spec = importlib.util.spec_from_file_location("cxpan_test_hub", MODULE)
hub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hub)


class HubTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_db, self.old_token = hub.DB, hub.TOKEN
        hub.DB = Path(self.temp.name) / "tasks.sqlite3"
        hub.TOKEN = Path(self.temp.name) / "token"
        hub.TOKEN.write_text("local-test-secret\n")
        self.addCleanup(self.reset)
        self.db = hub.connect()
        self.addCleanup(self.db.close)

    def reset(self):
        hub.DB, hub.TOKEN = self.old_db, self.old_token

    def payload(self):
        return {"idempotency_key": "p1-echo-test-001",
                "requester": "chatgpt.cxre", "project_id": "CX-PAN",
                "target": "echo.local", "capability": "echo",
                "goal": "Return a synthetic echo", "repo_id": "none"}

    def test_enqueue_unique_and_conflict(self):
        code, result = hub.enqueue(self.db, self.payload())
        self.assertEqual(code, 201)
        code2, again = hub.enqueue(self.db, self.payload())
        self.assertEqual(code2, 200)
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["task"]["task_id"], result["task"]["task_id"])
        conflict = self.payload()
        conflict["goal"] = "Different task content"
        self.assertEqual(hub.enqueue(self.db, conflict)[0], 409)
        self.assertEqual(self.db.execute("SELECT count(*) FROM tasks").fetchone()[0], 1)

    def test_claim_once_report_attempt_and_result(self):
        _, result = hub.enqueue(self.db, self.payload())
        args = {"worker_id": "wsl-worker", "targets": ["echo.local"]}
        code, c = hub.claim(self.db, args)
        self.assertEqual(code, 200)
        t = c["task"]
        self.assertEqual(t["task_id"], result["task"]["task_id"])
        self.assertEqual(hub.claim(self.db, args)[1]["task"], None)
        report = {
            "task_id": t["task_id"], "attempt_id": t["attempt_id"],
            "worker_id": "wsl-worker", "status": "COMPLETED",
            "run_id": "echo-run", "result_text": "ECHO_OK",
            "error_text": ""}
        bogus = dict(report, attempt_id="wrong-attempt")
        self.assertEqual(hub.report(self.db, bogus)[0], 409)
        self.assertEqual(hub.report(self.db, report)[0], 200)
        self.assertEqual(hub.report(self.db, report)[0], 409)
        row = self.db.execute(
            "SELECT status,result_text FROM tasks WHERE task_id=?",
            (t["task_id"],)).fetchone()
        self.assertEqual((row["status"], row["result_text"]),
                         ("COMPLETED", "ECHO_OK"))
        count = self.db.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id=?", (t["task_id"],)
        ).fetchone()[0]
        self.assertEqual(count, 3)

    def test_only_registered_capabilities(self):
        bad = self.payload()
        bad["target"] = "shell.root"
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, bad)
        bad = self.payload()
        bad["target"] = "claude.code.local"
        bad["capability"] = "repo.inspect"
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, bad)
        bad["repo_id"] = "agent-loop"
        self.assertEqual(hub.enqueue(self.db, bad)[0], 201)

    def test_heartbeat_marks_stale_running_without_replaying(self):
        _, created = hub.enqueue(self.db, self.payload())
        _, response = hub.claim(self.db, {
            "worker_id": "wsl-worker", "targets": ["echo.local"]
        })
        task = response["task"]
        self.db.execute(
            "UPDATE tasks SET updated_at='2020-01-01T00:00:00+00:00' WHERE task_id=?",
            (task["task_id"],)
        )
        self.db.commit()
        row = self.db.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task["task_id"],)
        ).fetchone()
        self.assertEqual(hub.public(row)["execution_health"], "STALE_NEEDS_REVIEW")
        heartbeat = {
            "task_id": task["task_id"], "attempt_id": task["attempt_id"],
            "worker_id": "wsl-worker"
        }
        self.assertEqual(
            hub.heartbeat(self.db, dict(heartbeat, attempt_id="unknown"))[0], 409
        )
        self.assertEqual(hub.heartbeat(self.db, heartbeat)[0], 200)
        row = self.db.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task["task_id"],)
        ).fetchone()
        self.assertEqual(hub.public(row)["execution_health"], "RUNNING_HEARTBEAT_OK")
        self.assertEqual(row["status"], "RUNNING")
        self.assertEqual(hub.report(self.db, {
            **heartbeat, "status": "COMPLETED", "run_id": "echo-done",
            "result_text": "done", "error_text": ""
        })[0], 200)
        self.assertEqual(hub.heartbeat(self.db, heartbeat)[0], 409)
        count = self.db.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id=?",
            (task["task_id"],)
        ).fetchone()[0]
        self.assertEqual(count, 3)

    def test_health_targets_are_explicit_read_only_capabilities(self):
        for target in ("hermes.health.local", "openclaw.health.local"):
            case = self.payload()
            case["idempotency_key"] = "check-" + target
            case["target"] = target
            case["capability"] = "gateway.health"
            result = hub.enqueue(self.db, case)
            self.assertEqual(result[0], 201)
            self.assertEqual(result[1]["task"]["capability"], "gateway.health")
        bad = self.payload()
        bad["target"] = "hermes.health.local"
        bad["capability"] = "repo.inspect"
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, bad)

    def test_repository_validate_target_needs_exact_capability(self):
        case = self.payload()
        case.update({
            "idempotency_key": "p3-repo-validation-001",
            "target": "repo.validate.local",
            "capability": "repo.validate",
            "repo_id": "agent-loop"
        })
        self.assertEqual(hub.enqueue(self.db, case)[0], 201)
        invalid = dict(case, idempotency_key="p3-bad-validation-001")
        invalid["repo_id"] = "none"
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, invalid)

    def test_hermes_model_is_text_review_without_repository_access(self):
        good = self.payload()
        good.update({
            "idempotency_key": "p4-hermes-readonly-0001",
            "target": "hermes.model.local",
            "capability": "text.review", "repo_id": "none",
        })
        self.assertEqual(hub.enqueue(self.db, good)[0], 201)
        forbidden = dict(good, idempotency_key="p4-hermes-invalid-0002", repo_id="agent-loop")
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, forbidden)
        mismatched = dict(good, idempotency_key="p4-hermes-invalid-0003", capability="repo.inspect")
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, mismatched)

    def test_immutable_parent_task_provenance_and_digest(self):
        parent_payload = dict(self.payload())
        parent_payload.update({
            "idempotency_key": "p5-parent-claude-0001",
            "target": "claude.code.local", "capability": "repo.inspect",
            "repo_id": "agent-loop",
        })
        _, created = hub.enqueue(self.db, parent_payload)
        parent_id = created["task"]["task_id"]
        _, claim_result = hub.claim(
            self.db, {"worker_id": "claude", "targets": ["claude.code.local"]}
        )
        claimed = claim_result["task"]
        source_text = "CLAUDE_SOURCE_CONTENT_" + "factual source " * 18
        result = hub.report(self.db, {
            "task_id": parent_id,
            "attempt_id": claimed["attempt_id"],
            "worker_id": "claude",
            "status": "COMPLETED",
            "run_id": "claude-native-0001",
            "result_text": source_text,
            "error_text": "",
        })
        self.assertEqual(result[0], 200)
        digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        child = dict(self.payload())
        child.update({
            "idempotency_key": "p5-reviewed-child-0001",
            "target": "hermes.model.local",
            "capability": "text.review",
            "repo_id": "none",
            "goal": "Independently review this quoted data: " + source_text,
            "parent_task_id": parent_id,
            "source_sha256": digest,
        })
        code, created_child = hub.enqueue(self.db, child)
        self.assertEqual(code, 201)
        child_id = created_child["task"]["task_id"]
        link = self.db.execute(
            "SELECT parent_task_id,source_sha256 FROM task_provenance WHERE child_task_id=?",
            (child_id,)
        ).fetchone()
        self.assertEqual((link[0], link[1]), (parent_id, digest))
        duplicate = hub.enqueue(self.db, child)
        self.assertEqual(duplicate[0], 200)
        self.assertTrue(duplicate[1]["duplicate"])
        count = self.db.execute(
            "SELECT COUNT(*) FROM task_provenance WHERE child_task_id=?", (child_id,)
        ).fetchone()[0]
        self.assertEqual(count, 1)

        bad_sha = dict(child, idempotency_key="p5-bad-sha-0001",
                       source_sha256="0"*64)
        self.assertEqual(hub.enqueue(self.db, bad_sha)[0], 409)
        bad_text = dict(child, idempotency_key="p5-bad-quote-0001",
                        goal="Falsely claims this is the source text")
        self.assertEqual(hub.enqueue(self.db, bad_text)[0], 409)
        bad_project = dict(child, idempotency_key="p5-bad-project-0001",
                           project_id="NOT-CX-PAN")
        self.assertEqual(hub.enqueue(self.db, bad_project)[0], 409)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM tasks WHERE target='hermes.model.local'"
        ).fetchone()[0], 1)

    def test_provenance_pair_and_target_validation(self):
        original = self.payload()
        original["parent_task_id"] = "a"*36
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, original)
        original["source_sha256"] = "b"*64
        with self.assertRaises(ValueError):
            hub.enqueue(self.db, original)

    def test_openclaw_cloud_provenance_requires_completed_hermes_parent(self):
        parent = dict(self.payload())
        parent.update({
            "idempotency_key": "p5-hermes-parent-0001",
            "target": "hermes.model.local", "capability": "text.review",
            "repo_id": "none",
        })
        _, record = hub.enqueue(self.db, parent)
        hermes_id = record["task"]["task_id"]
        text = "Hermes independent assessment: " + "verify sources. " * 15
        _, owned = hub.claim(self.db, {
            "worker_id": "hermes", "targets": ["hermes.model.local"]
        })
        t = owned["task"]
        self.assertEqual(hub.report(self.db, {
            "task_id": t["task_id"], "attempt_id": t["attempt_id"],
            "worker_id": "hermes", "status": "COMPLETED",
            "run_id": "hermes-one-shot-example", "result_text": text,
            "error_text": ""
        })[0], 200)
        child = dict(self.payload())
        child.update({
            "idempotency_key": "p5-openclaw-child-0001",
            "target": "openclaw.model.cloud", "capability": "text.review",
            "repo_id": "none", "goal": "Review excerpt: " + text,
            "parent_task_id": hermes_id,
            "source_sha256": hashlib.sha256(text.encode()).hexdigest()
        })
        status, res = hub.enqueue(self.db, child)
        self.assertEqual(status, 201)
        link = self.db.execute(
            "SELECT parent_task_id,source_sha256 FROM task_provenance WHERE child_task_id=?",
            (res["task"]["task_id"],)
        ).fetchone()
        self.assertEqual((link[0], link[1]),
                         (hermes_id, child["source_sha256"]))
        bad = dict(child, idempotency_key="p5-invalid-child-0002",
                   source_sha256="0"*64)
        self.assertEqual(hub.enqueue(self.db, bad)[0], 409)

    def test_http_auth_and_end_to_end(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), hub.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"

        def api(path, data=None, token="local-test-secret"):
            headers = {"Authorization": f"Bearer {token}"}
            if data is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(
                base + path, method="POST" if data is not None else "GET",
                data=json.dumps(data).encode() if data is not None else None,
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                return json.load(resp)

        with self.assertRaises(urllib.error.HTTPError) as context:
            api("/v1/agents", token="invalid")
        self.assertEqual(context.exception.code, 401)
        created = api("/v1/tasks", self.payload())["task"]
        self.assertEqual(api("/v1/tasks/" + created["task_id"])["task"]["status"], "QUEUED")
        task = api("/v1/workers/claim", {
            "worker_id": "wsl-worker", "targets": ["echo.local"]
        })["task"]
        self.assertEqual(task["task_id"], created["task_id"])
        api("/v1/workers/report", {
            "task_id": task["task_id"], "attempt_id": task["attempt_id"],
            "worker_id": "wsl-worker", "status": "COMPLETED",
            "run_id": "echo-run", "result_text": "ECHO_OK HTTP",
            "error_text": ""
        })
        res = api("/v1/tasks/" + task["task_id"] + "/result")
        self.assertEqual(res["result_text"], "ECHO_OK HTTP")


if __name__ == "__main__":
    unittest.main()
