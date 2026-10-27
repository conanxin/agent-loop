#!/usr/bin/env python3
"""P7 MCP security and safe client exchange contract tests; no live network."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
import mcp_gateway as gateway

CHATGPT_TOKEN = "p7-test-only-chatgpt-secret"
CLAUDE_TOKEN = "p7-test-only-claude-secret"
IDENTITY = "00000000-1111-2222-3333-444444444444"
LEGACY_ID = "00000000-1111-2222-3333-555555555555"


class RestrictedMCPTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        credentials = root / "clients.json"
        credentials.write_text(json.dumps({
            "chatgpt": hashlib.sha256(CHATGPT_TOKEN.encode()).hexdigest(),
            "claude": hashlib.sha256(CLAUDE_TOKEN.encode()).hexdigest(),
        }))
        self.old_file, self.old_db = gateway.CLIENTS, gateway.QUOTA_DB
        gateway.CLIENTS = credentials
        gateway.QUOTA_DB = root / "quotas.sqlite3"
        self.addCleanup(self.restore)
        self.logged_calls = []
        self.model_task_access_attempted = False
        self.mock_rpc = patch.object(gateway, "mcp_rpc", side_effect=self.fake_rpc)
        self.mock_rpc.start()
        self.addCleanup(self.mock_rpc.stop)
        self.client = TestClient(gateway.create_app(),
                                 base_url="http://127.0.0.1:18488")
        self.client.__enter__()
        self.addCleanup(lambda: self.client.__exit__(None, None, None))

    def restore(self):
        gateway.CLIENTS, gateway.QUOTA_DB = self.old_file, self.old_db

    def fake_rpc(self, method, path, data=None):
        self.logged_calls.append((method, path, data))
        if path.endswith(LEGACY_ID):
            return {"task": {
                "task_id": LEGACY_ID, "project_id": "CX-PAN",
                "requester": "chatgpt.cxre", "target": "claude.code.local",
                "status": "COMPLETED", "run_id": "legacy"}},
        if method == "POST":
            if data["target"] not in gateway.SAFE_TARGETS:
                self.model_task_access_attempted = True
            return {"task": {
                "task_id": IDENTITY, "target": data["target"],
                "status": "QUEUED"}, "duplicate": False}
        row = {
            "task_id": IDENTITY, "project_id": "CX-PAN",
            "requester": "mcp.chatgpt", "target": "echo.local",
            "status": "COMPLETED", "run_id": "echo-only"}
        if path.endswith("/result"):
            return {"task": row, "result_text": "ECHO_OK safe response",
                    "error_text": ""}
        return {"task": row}

    def rpc(self, principal, method, params=None, token=None, origin=None):
        if token is None:
            token = CHATGPT_TOKEN if principal == "chatgpt" else CLAUDE_TOKEN
        payload = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
        }
        if origin:
            headers["Origin"] = origin
        return self.client.post(f"/{principal}/mcp", json=payload,
                                headers=headers)

    def test_each_client_can_initialize_without_sharing_credential(self):
        init = {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "P7 isolated test", "version": "0.1"}
        }
        for principal in ("chatgpt", "claude"):
            result = self.rpc(principal, "initialize", init)
            self.assertEqual(result.status_code, 200, result.text[:350])
            self.assertEqual(result.json()["result"]["protocolVersion"], "2025-11-25")
        crossed = self.rpc("claude", "initialize", init, token=CHATGPT_TOKEN)
        self.assertEqual(crossed.status_code, 401)
        crossed = self.rpc("chatgpt", "initialize", init, token=CLAUDE_TOKEN)
        self.assertEqual(crossed.status_code, 401)

    def test_no_token_wrong_origin_and_bad_routes(self):
        result = self.client.post(
            "/chatgpt/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        self.assertEqual(result.status_code, 401)
        blocked = self.rpc("claude", "tools/list", origin="https://evil.example")
        self.assertEqual(blocked.status_code, 403)
        accepted = self.rpc("claude", "tools/list", origin="https://claude.ai")
        self.assertEqual(accepted.status_code, 200)
        missing = self.client.post("/missing/mcp", json={})
        self.assertEqual(missing.status_code, 404)

    def test_tool_registry_does_not_advertise_any_agent_shell_or_paid_model(self):
        for principal in ("chatgpt", "claude"):
            result = self.rpc(principal, "tools/list")
            self.assertEqual(result.status_code, 200)
            names = [tool["name"] for tool in result.json()["result"]["tools"]]
            self.assertEqual(set(names),
                             {"agents_list", "task_get", "task_result",
                              "task_submit_safe"})
            for item in result.json()["result"]["tools"]:
                annotations=item.get("annotations") or {}
                expected_read_only=item["name"]!="task_submit_safe"
                self.assertEqual(
                    annotations.get("readOnlyHint"),expected_read_only,
                    item["name"]
                )
                self.assertFalse(annotations.get("destructiveHint"))
            # The task-submit tool creates a ledger work item; it cannot be
            # misrepresented as read-only to ChatGPT or Claude plans.
            caps = self.rpc(principal, "tools/call", {
                "name": "agents_list", "arguments": {}
            })
            self.assertEqual(caps.status_code, 200)
            self.assertNotIn("exec", json.dumps(caps.json()))
            self.assertIn("repo.evidence.local", json.dumps(caps.json()))

    def test_two_clients_submit_bounded_safe_tasks_and_read_same_result(self):
        for principal in ("chatgpt", "claude"):
            key = f"p7-{principal}-first-20261026"
            post = self.rpc(principal, "tools/call", {
                "name": "task_submit_safe", "arguments": {
                    "target": "echo.local", "goal": "Harmless MCP echo test",
                    "idempotency_key": key,
                }
            })
            self.assertEqual(post.status_code, 200)
            self.assertFalse(post.json()["result"].get("isError", False))
        methods = [(v[0], v[2]) for v in self.logged_calls if v[0] == "POST"]
        self.assertEqual(len(methods), 2)
        self.assertEqual({x["requester"] for _, x in methods},
                         {"mcp.chatgpt", "mcp.claude"})
        self.assertTrue(all(x["target"] == "echo.local" for _, x in methods))
        self.assertTrue(all(x["capability"] == "echo" for _, x in methods))
        for principal in ("chatgpt", "claude"):
            result = self.rpc(principal, "tools/call", {
                "name": "task_result", "arguments": {"task_id": IDENTITY}
            })
            self.assertEqual(result.status_code, 200)
            self.assertIn("ECHO_OK safe response", json.dumps(result.json()))

    def test_historical_private_task_is_hidden_even_with_valid_uuid(self):
        result = self.rpc("chatgpt", "tools/call", {
            "name": "task_get", "arguments": {"task_id": LEGACY_ID}
        })
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["result"].get("isError"))
        self.assertNotIn("legacy", json.dumps(result.json()))

    def test_arbitrary_path_is_rejected_without_upstream_submission(self):
        rejected = self.rpc("claude", "tools/call", {
            "name": "task_submit_safe", "arguments": {
                "target": "repo.evidence.local",
                "goal": "../../.ssh/id_rsa",
                "idempotency_key": "test_bad_capture_0001",
            }
        })
        self.assertEqual(rejected.status_code, 200)
        self.assertTrue(rejected.json()["result"].get("isError"))
        self.assertEqual(len(self.logged_calls), 0)

    def test_quota_daily_and_duplicate_key(self):
        for i in range(gateway.MAX_DAILY_UNIQUE):
            gateway.quota_slot("chatgpt", f"test-slot-{i}")
        gateway.quota_slot("chatgpt", "test-slot-0")
        with self.assertRaisesRegex(ValueError, "quota reached"):
            gateway.quota_slot("chatgpt", "one-too-many")
        # Independently scoped Claude token retains its own quota.
        gateway.quota_slot("claude", "can-submit")


if __name__ == "__main__":
    unittest.main()
