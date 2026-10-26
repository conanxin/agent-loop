#!/usr/bin/env python3
"""Cloud queue contract and HTTP regression tests, all using temporary files."""
import importlib.util
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
