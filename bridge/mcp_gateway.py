#!/usr/bin/env python3
"""P7 restricted MCP gateway for CX-PAN cloud task ledger.

Clients: independent ChatGPT / Claude bearer tokens, per-principal scopes,
fixed small capabilities, no general shell/model execution and no access to
historical private work. Public HTTPS must terminate at a trusted reverse
proxy; this service listens ONLY on 127.0.0.1.

Upstream master Hub token NEVER reaches external MCP clients.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import urllib.error
import urllib.request
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from oauth_store import RESOURCE as OAUTH_RESOURCE
from oauth_store import SCOPE as OAUTH_SCOPE
from oauth_store import PI_SCOPE, PI_RESOURCE
from oauth_store import verify_access as verify_oauth_access

HOME = Path.home()
CLIENTS = Path(os.getenv(
    "CX_PAN_MCP_CLIENTS_FILE", str(HOME / ".config/cx-pan/mcp_clients.json")))
HUB_TOKEN_FILE = Path(os.getenv(
    "CX_PAN_MCP_HUB_TOKEN_FILE", str(HOME / ".config/cx-pan/token")))
HUB_URL = os.getenv("CX_PAN_MCP_HUB_URL", "http://127.0.0.1:18487").rstrip("/")
QUOTA_DB = Path(os.getenv(
    "CX_PAN_MCP_QUOTA_DB", str(HOME / ".local/share/cx-pan/mcp_quota.sqlite3")))
MCP_HOST = "127.0.0.1"
MCP_PORT = int(os.getenv("CX_PAN_MCP_PORT", "18488"))
EXTERNAL_PATHS = {
    "chatgpt": "/chatgpt/mcp",
    "chatgpt-pi": "/chatgpt-pi/mcp",
    "claude": "/claude/mcp",
}
ALLOWED_ORIGINS = {
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://claude.ai",
    "https://www.claude.ai",
}
SAFE_TARGETS = {"echo.local": "echo", "repo.evidence.local": "source.capture"}
SAFE_SOURCE_FILES = {"README.md", "docs/SPEC.md", "docs/SCHEMAS.md"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,36}$")
MAX_DAILY_UNIQUE = 20
MCP_ACTORS = ("mcp.chatgpt", "mcp.claude")
VERSION = "2025-11-25"


def load_client_hashes():
    data = json.loads(CLIENTS.read_text(encoding="utf-8"))
    if set(data) != {"chatgpt","claude"}:
        raise RuntimeError("MCP client registry must contain chatgpt and claude")
    for name, val in data.items():
        if not isinstance(val, str) or not re.fullmatch("[0-9a-f]{64}", val):
            raise RuntimeError("invalid MCP client hash for " + name)
    return data


def mcp_rpc(method, path, payload=None):
    # This is a private upstream connection; never forward caller Authorization.
    token = HUB_TOKEN_FILE.read_text(encoding="utf-8").strip()
    body = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None else None)
    request = urllib.request.Request(
        HUB_URL + path,
        method=method, data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Explicitly avoid returning upstream task text, credentials, headers.
        if exc.code == 404:
            raise ValueError("task not found") from exc
        if exc.code == 409:
            raise ValueError("task conflicts with a prior idempotency key") from exc
        raise RuntimeError(f"CX-PAN task hub HTTP {exc.code}") from exc


def check_visible(record):
    task = record.get("task")
    if not isinstance(task, dict) or (
        task.get("project_id") != "CX-PAN" or
        task.get("requester") not in MCP_ACTORS or
        task.get("target") not in SAFE_TARGETS
    ):
        raise ValueError("task not found")
    return task


def quota_slot(principal, key):
    """Atomic per-principal/day quota; duplicate calls share the same slot."""
    QUOTA_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(QUOTA_DB, timeout=5)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS quotas (
          client TEXT NOT NULL,
          day TEXT NOT NULL,
          idem_key TEXT NOT NULL,
          PRIMARY KEY (client, day, idem_key)
        )
        """)
        day = datetime.now(timezone.utc).date().isoformat()
        conn.execute("BEGIN IMMEDIATE")
        record = conn.execute(
            "SELECT 1 FROM quotas WHERE client=? AND day=? AND idem_key=?",
            (principal, day, key)).fetchone()
        if record:
            conn.commit()
            return
        count = conn.execute(
            "SELECT count(*) FROM quotas WHERE client=? AND day=?",
            (principal, day)).fetchone()[0]
        if count >= MAX_DAILY_UNIQUE:
            conn.rollback()
            raise ValueError("daily new task quota reached for this client")
        conn.execute(
            "INSERT INTO quotas(client,day,idem_key) VALUES(?,?,?)",
            (principal, day, key))
        conn.commit()
    finally:
        conn.close()


class OAuthToolFastMCP(FastMCP):
    """Expose per-tool OAuth scopes to ChatGPT while retaining BearerGate."""

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.securitySchemes = [{"type": "oauth2", "scopes": [
                PI_SCOPE if getattr(self, "_pi_oauth", False) else OAUTH_SCOPE
            ]}]
        return tools


def tools_for(principal):
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*", "localhost:*", "www.conanxin.com",
            "www.conanxin.com:443",
        ],
        allowed_origins=sorted(ALLOWED_ORIGINS),
    )
    server = (OAuthToolFastMCP if principal in ("chatgpt", "chatgpt-pi") else FastMCP)(
        f"CX-PAN {principal} restricted connector",
        instructions=(
            "Safe user-controlled personal AI task status. Only read P7 "
            "tasks created by chatgpt or claude restricted MCP clients. "
            "Task submission may only create echo or allowlisted public "
            "source-capture tasks, never paid model calls or shell commands."
        ),
        stateless_http=True, json_response=True,
        transport_security=security,
    )

    if principal == "chatgpt-pi":
        server._pi_oauth = True

        def _pi_visible(receipt):
            t = receipt.get("task")
            if not isinstance(t, dict) or (
                t.get("target") != "pi.text.cloud" or
                t.get("capability") != "pi.text" or
                t.get("project_id") != "CX-PAN" or
                t.get("requester") != "mcp.chatgpt.pi"
            ):
                raise ValueError("task not found")
            return t

        @server.tool(
            name="pi_capabilities",
            description="Read this separately authorized Pi text-only tool and its limits.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                        openWorldHint=False),
        )
        def pi_capabilities() -> dict:
            return {
                "agent": "xinhailin / Pi 1.4.0",
                "model": "minimax-cn/MiniMax-M2.7",
                "mode": "text-only/no-tools/no-mcp/no-session",
                "may_consume_model_allowance": True,
                "max_new_model_tasks_per_utc_day": 6,
                "max_input_characters": 1200,
                "permissions": ["tasks:pi_text"],
                "can_run_shell": False,
                "can_read_private_files": False,
            }

        @server.tool(
            name="pi_text_submit",
            description=("Submit one bounded MiniMax Pi TEXT-only task to the "
                         "owner's Windows laptop. Consumes model allowance; "
                         "no Shell, files, MCP or sessions. A stable "
                         "idempotency_key prevents duplicate model runs."),
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                        idempotentHint=True, openWorldHint=True),
        )
        def pi_text_submit(goal: str, idempotency_key: str) -> dict:
            if not isinstance(goal, str) or not (4 <= len(goal) <= 1200):
                raise ValueError("Pi task text must contain 4..1200 characters")
            if not IDENTIFIER.fullmatch(idempotency_key) or len(idempotency_key)>90:
                raise ValueError("idempotency_key must be 8..90 safe ASCII characters")
            response = mcp_rpc("POST", "/v1/tasks", {
                "idempotency_key": "p10-pi-" + idempotency_key,
                "requester": "mcp.chatgpt.pi",
                "project_id": "CX-PAN",
                "target": "pi.text.cloud",
                "capability": "pi.text",
                "goal": goal, "repo_id": "none"
            })
            t = response["task"]
            return {"task_id": t["task_id"], "status": t["status"],
                    "duplicate": response["duplicate"], "target": t["target"]}

        @server.tool(
            name="pi_text_get",
            description="Read the execution state of an authorized Pi text task.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                        openWorldHint=False),
        )
        def pi_text_get(task_id: str) -> dict:
            if not UUID.fullmatch(task_id):
                raise ValueError("invalid task_id")
            t = _pi_visible(mcp_rpc("GET", f"/v1/tasks/{task_id}"))
            return {"task_id": t["task_id"], "status": t["status"],
                    "execution_health": t.get("execution_health"),
                    "run_id": t.get("run_id"), "target": t["target"]}

        @server.tool(
            name="pi_text_result",
            description="Read a completed, separately authorized Pi text answer.",
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                        openWorldHint=False),
        )
        def pi_text_result(task_id: str) -> dict:
            if not UUID.fullmatch(task_id):
                raise ValueError("invalid task_id")
            obj=mcp_rpc("GET", f"/v1/tasks/{task_id}/result")
            t = _pi_visible(obj)
            return {
                "task_id": t["task_id"], "status": t["status"],
                "result_text": (obj.get("result_text") or "")[:16500],
                "error": (obj.get("error_text") or "")[:500],
                "run_id": t.get("run_id")
            }

        return server

    @server.tool(
        name="agents_list",
        description="List only the two SAFE submit capabilities of CX-PAN.",
        annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,
                                    openWorldHint=False),
    )
    def agents_list() -> dict:
        return {
            "principal": principal,
            "safe_targets": [
                {"id": "echo.local", "capability": "echo", "cost": "no model"},
                {"id": "repo.evidence.local", "capability": "source.capture",
                 "allowed_sources": sorted(SAFE_SOURCE_FILES), "cost": "no model"},
            ],
            "can_submit_paid_model_tasks": False,
            "daily_new_task_limit": MAX_DAILY_UNIQUE,
        }

    @server.tool(
        name="task_get",
        description="Inspect an authorized P7 task by its task_id.",
        annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,
                                    openWorldHint=False),
    )
    def task_get(task_id: str) -> dict:
        if not UUID.fullmatch(task_id):
            raise ValueError("invalid task_id")
        result = mcp_rpc("GET", f"/v1/tasks/{task_id}")
        t = check_visible(result)
        return {
            "task_id": t["task_id"], "status": t["status"],
            "execution_health": t.get("execution_health"),
            "target": t["target"], "requester": t["requester"],
            "run_id": t.get("run_id"),
        }

    @server.tool(
        name="task_result",
        description="Read the stored result of a completed authorized P7 task.",
        annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,
                                    openWorldHint=False),
    )
    def task_result(task_id: str) -> dict:
        if not UUID.fullmatch(task_id):
            raise ValueError("invalid task_id")
        result = mcp_rpc("GET", f"/v1/tasks/{task_id}/result")
        t = check_visible(result)
        data = result.get("result_text")
        return {
            "task_id": t["task_id"], "status": t["status"],
            "target": t["target"], "run_id": t.get("run_id"),
            # Only the safe echo/public source capture target can reach here.
            "result_text": data[:19500] if isinstance(data, str) else None,
            "error": (result.get("error_text") or "")[:450],
        }

    @server.tool(
        name="task_submit_safe",
        description=(
            "Submit only a bounded echo or a whitelisted PUBLIC agent-loop "
            "document capture. Requires a caller-chosen stable idempotency_key. "
            "No paid model invocation, file edits, arbitrary paths or shell."
        ),
        annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,
                                    idempotentHint=True,openWorldHint=False),
    )
    def task_submit_safe(
        target: Literal["echo.local", "repo.evidence.local"],
        goal: str,
        idempotency_key: str,
    ) -> dict:
        if target not in SAFE_TARGETS:
            raise ValueError("target not in safe capability allowlist")
        if not IDENTIFIER.fullmatch(idempotency_key) or len(idempotency_key) > 100:
            raise ValueError("invalid idempotency_key: use 8..100 ASCII letters/numbers/_/-")
        if not isinstance(goal, str) or not (4 <= len(goal) <= 420):
            raise ValueError("safe task goal must be 4..420 characters")
        if target == "repo.evidence.local" and goal not in SAFE_SOURCE_FILES:
            raise ValueError("capture is limited to three allowlisted public files")
        quota_slot(principal, idempotency_key)
        response = mcp_rpc("POST", "/v1/tasks", {
            "idempotency_key": "p7-" + principal + "-" + idempotency_key,
            "requester": "mcp." + principal,
            "project_id": "CX-PAN",
            "target": target,
            "capability": SAFE_TARGETS[target],
            "goal": goal,
            "repo_id": "agent-loop" if target == "repo.evidence.local" else "none",
        })
        t = response["task"]
        return {"task_id": t["task_id"], "status": t["status"],
                "target": t["target"], "duplicate": response["duplicate"]}

    return server


class BearerGate:
    """Pure ASGI middleware (streaming-safe) in front of both MCP apps."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def scope_client(path):
        parts = path.split("/")
        if len(parts) >= 3 and parts[1] in EXTERNAL_PATHS:
            return parts[1]
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path == "/healthz":
            await self.app(scope, receive, send)
            return
        name = self.scope_client(path)
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("utf-8", errors="replace")
        if origin and origin not in ALLOWED_ORIGINS:
            response = JSONResponse({"error": "forbidden origin"}, status_code=403)
            await response(scope, receive, send)
            return
        if name is None:
            response = JSONResponse({"error": "not found"}, status_code=404)
            await response(scope, receive, send)
            return
        auth = headers.get(b"authorization", b"").decode("utf-8", errors="replace")
        expected_digest = load_client_hashes().get(name)
        supplied = auth.removeprefix("Bearer ")
        valid = (
            expected_digest is not None and
            auth.startswith("Bearer ") and len(supplied) <= 256 and
            hmac.compare_digest(
                hashlib.sha256(supplied.encode("utf-8")).hexdigest(),
                expected_digest,
            )
        )
        # ChatGPT's native plugin cannot supply an arbitrary API key. P8
        # additionally accepts a short-lived, scope/audience-checked OAuth
        # access token. Claude continues to use its separate P7 credential.
        if name in ("chatgpt", "chatgpt-pi") and not valid and auth.startswith("Bearer "):
            valid = verify_oauth_access(
                supplied,
                resource=(PI_RESOURCE if name == "chatgpt-pi" else OAUTH_RESOURCE),
                scope=(PI_SCOPE if name == "chatgpt-pi" else OAUTH_SCOPE),
            )
        if not valid:
            metadata = (
                'Bearer resource_metadata="https://www.conanxin.com/'
                '.well-known/oauth-protected-resource/cxpan/chatgpt-pi/mcp", '
                'scope="tasks:pi_text", error="invalid_token"'
                if name == "chatgpt-pi" else (
                    'Bearer resource_metadata="https://www.conanxin.com/'
                    '.well-known/oauth-protected-resource/cxpan/chatgpt/mcp", '
                    'scope="tasks:safe", error="invalid_token", '
                    'error_description="CX-PAN OAuth connection required"'
                    if name == "chatgpt" else 'Bearer realm="CX-PAN restricted MCP"'
                )
            )
            response = JSONResponse({"error": "unauthorized"}, status_code=401,
                headers={"WWW-Authenticate": metadata})
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def healthz(_):
    return JSONResponse({"ok": True, "name": "cx-pan-restricted-mcp",
                         "public_bearer_required": True})


def create_app():
    servers = {p: tools_for(p) for p in EXTERNAL_PATHS}
    # Create mounted ASGI apps before starting their session managers.
    mounted = {p: s.streamable_http_app() for p, s in servers.items()}

    @asynccontextmanager
    async def lifespan(_app):
        async with AsyncExitStack() as stack:
            for server in servers.values():
                await stack.enter_async_context(server.session_manager.run())
            yield

    inner = Starlette(
        routes=[
            Route("/healthz", healthz),
            Mount("/chatgpt", mounted["chatgpt"]),
            Mount("/chatgpt-pi", mounted["chatgpt-pi"]),
            Mount("/claude", mounted["claude"]),
        ],
        lifespan=lifespan,
    )
    return BearerGate(inner)


if __name__ == "__main__":
    if os.getenv("CX_PAN_MCP_HOST", "127.0.0.1") != "127.0.0.1":
        raise SystemExit("P7 MCP must bind to loopback only")
    # Fail closed if registry/upstream secret is missing.
    load_client_hashes()
    if not HUB_TOKEN_FILE.exists():
        raise SystemExit("missing private upstream Hub token")
    app = create_app()
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, log_level="warning",
                access_log=False)
