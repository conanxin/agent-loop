#!/usr/bin/env python3
"""CX-PAN P1: tiny authenticated, loopback-only task hub.

No model access, no shell execution, no Agent gateway access. Requires an SSH
forward or authorized private transport to access from another computer.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HOME = Path.home()
DB = Path(os.environ.get("CX_PAN_DB", str(HOME / ".local/share/cx-pan/tasks.sqlite3")))
TOKEN = Path(os.environ.get("CX_PAN_TOKEN_FILE", str(HOME / ".config/cx-pan/token")))
TARGETS = {
    "echo.local": "echo",
    "claude.code.local": "repo.inspect",
    "hermes.health.local": "gateway.health",
    "openclaw.health.local": "gateway.health",
    "repo.validate.local": "repo.validate",
    "hermes.model.local": "text.review",
    "openclaw.model.cloud": "text.review",
}
PARENT_TARGETS = {
    "hermes.model.local": "claude.code.local",
    "openclaw.model.cloud": "hermes.model.local",
}

STALE_AFTER_SECONDS = 180
MAX_BODY = 65536


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
          task_id TEXT PRIMARY KEY,
          idempotency_key TEXT NOT NULL UNIQUE,
          fingerprint TEXT NOT NULL,
          requester TEXT NOT NULL,
          project_id TEXT NOT NULL,
          target TEXT NOT NULL,
          capability TEXT NOT NULL,
          goal TEXT NOT NULL,
          repo_id TEXT NOT NULL,
          status TEXT NOT NULL,
          worker_id TEXT,
          attempt_id TEXT,
          run_id TEXT,
          result_text TEXT,
          error_text TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_events(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          at TEXT NOT NULL,
          note TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_provenance(
          child_task_id TEXT PRIMARY KEY,
          parent_task_id TEXT NOT NULL,
          source_sha256 TEXT NOT NULL
        );
    """)
    return db


def public(row):
    keys = ("task_id", "requester", "project_id", "target", "capability",
            "goal", "repo_id", "status", "worker_id", "run_id",
            "created_at", "updated_at")
    result = {k: row[k] for k in keys}
    if row["status"] == "RUNNING":
        updated = datetime.fromisoformat(row["updated_at"])
        age = max(0, (datetime.now(timezone.utc) - updated).total_seconds())
        result["execution_health"] = (
            "STALE_NEEDS_REVIEW" if age > STALE_AFTER_SECONDS else "RUNNING_HEARTBEAT_OK"
        )
        result["seconds_since_heartbeat"] = int(age)
    else:
        result["execution_health"] = (
            "WAITING_FOR_WORKER" if row["status"] == "QUEUED"
            else "FINISHED" if row["status"] in ("COMPLETED", "FAILED") else "UNKNOWN"
        )
    return result


def valid_submit(body):
    if not isinstance(body, dict):
        raise ValueError("expected JSON object")
    allowed = {"idempotency_key", "requester", "project_id", "target",
               "capability", "goal", "repo_id", "parent_task_id",
               "source_sha256"}
    if set(body) - allowed:
        raise ValueError("unknown input fields")
    target = body.get("target")
    cap = body.get("capability")
    if target not in TARGETS or cap != TARGETS[target]:
        raise ValueError("unregistered target/capability")
    goal = body.get("goal")
    idem = body.get("idempotency_key")
    if not isinstance(goal, str) or not (4 <= len(goal) <= 3000):
        raise ValueError("goal must be 4 to 3000 characters")
    if not isinstance(idem, str) or not (8 <= len(idem) <= 128):
        raise ValueError("idempotency_key must be 8 to 128 characters")
    requester = body.get("requester", "cxpan.cli")
    project_id = body.get("project_id", "CX-PAN")
    repo_id = body.get("repo_id", "none")
    if not all(isinstance(s, str) and 1 <= len(s) <= 100
               for s in (requester, project_id, repo_id)):
        raise ValueError("invalid requester/project_id/repo_id")
    if target in ("claude.code.local", "repo.validate.local") and repo_id != "agent-loop":
        raise ValueError("repository capabilities only allow repo_id=agent-loop")
    if target not in ("claude.code.local", "repo.validate.local") and repo_id != "none":
        raise ValueError("non-repository targets require repo_id=none")
    parent_id = body.get("parent_task_id")
    sha = body.get("source_sha256")
    if (parent_id is None) != (sha is None):
        raise ValueError("provenance requires both parent_task_id and source_sha256")
    if parent_id is not None:
        if target not in PARENT_TARGETS:
            raise ValueError("P5 provenance requires registered text.review target")
        if not isinstance(parent_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", parent_id):
            raise ValueError("invalid parent_task_id")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("invalid source_sha256")
    return {
        "idempotency_key": idem, "requester": requester, "project_id": project_id,
        "target": target, "capability": cap, "goal": goal, "repo_id": repo_id,
        **({"parent_task_id": parent_id, "source_sha256": sha}
           if parent_id is not None else {})
    }


def enqueue(db, payload):
    payload = valid_submit(payload)
    fingerprint = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True
    ).encode()).hexdigest()
    db.execute("BEGIN IMMEDIATE")
    existing = db.execute(
        "SELECT * FROM tasks WHERE idempotency_key=?",
        (payload["idempotency_key"],)
    ).fetchone()
    if existing:
        if existing["fingerprint"] != fingerprint:
            db.rollback()
            return 409, {"error": "idempotency key conflict"}
        db.commit()
        return 200, {"task": public(existing), "duplicate": True}
    if "parent_task_id" in payload:
        parent = db.execute(
            "SELECT task_id, project_id, target, status, result_text FROM tasks WHERE task_id=?",
            (payload["parent_task_id"],)
        ).fetchone()
        if not parent or parent["status"] != "COMPLETED" or (
            parent["project_id"] != payload["project_id"] or
            parent["target"] != PARENT_TARGETS[payload["target"]] or
            not parent["result_text"]
        ):
            db.rollback()
            return 409, {"error": "parent must be a completed authorized upstream task in same project"}
        source = parent["result_text"]
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if digest != payload["source_sha256"] or source[:min(100, len(source))] not in payload["goal"]:
            db.rollback()
            return 409, {"error": "parent content digest or quoted source mismatch"}
    task_id, at = str(uuid.uuid4()), stamp()
    db.execute("""INSERT INTO tasks(
        task_id, idempotency_key, fingerprint, requester, project_id, target,
        capability, goal, repo_id, status, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (task_id, payload["idempotency_key"], fingerprint, payload["requester"],
         payload["project_id"], payload["target"], payload["capability"],
         payload["goal"], payload["repo_id"], "QUEUED", at, at))
    if "parent_task_id" in payload:
        db.execute(
            "INSERT INTO task_provenance(child_task_id,parent_task_id,source_sha256) "
            "VALUES(?,?,?)",
            (task_id, payload["parent_task_id"], payload["source_sha256"])
        )
    db.execute("INSERT INTO task_events(task_id,kind,at,note) VALUES(?,?,?,?)",
               (task_id, "QUEUED", at, payload["target"]))
    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    return 201, {"task": public(row), "duplicate": False}


def claim(db, payload):
    if not isinstance(payload, dict) or set(payload) != {"worker_id", "targets"}:
        raise ValueError("worker_id and targets required")
    who, targets = payload["worker_id"], payload["targets"]
    if not isinstance(who, str) or not (1 <= len(who) <= 100):
        raise ValueError("invalid worker_id")
    if not isinstance(targets, list) or not targets or (
        any(t not in TARGETS for t in targets)
    ):
        raise ValueError("invalid targets")
    db.execute("BEGIN IMMEDIATE")
    q = ",".join("?" for _ in targets)
    row = db.execute(
        f"SELECT * FROM tasks WHERE status='QUEUED' AND target IN ({q}) "
        "ORDER BY created_at, task_id LIMIT 1", tuple(targets)
    ).fetchone()
    if row is None:
        db.commit()
        return 200, {"task": None}
    attempt, at = str(uuid.uuid4()), stamp()
    db.execute(
        "UPDATE tasks SET status='RUNNING', worker_id=?, attempt_id=?, "
        "updated_at=? WHERE task_id=? AND status='QUEUED'",
        (who, attempt, at, row["task_id"]))
    db.execute("INSERT INTO task_events(task_id,kind,at,note) VALUES(?,?,?,?)",
               (row["task_id"], "CLAIMED", at, who))
    db.commit()
    return 200, {"task": {**public(row), "status": "RUNNING",
                         "attempt_id": attempt, "worker_id": who}}


def heartbeat(db, payload):
    required = {"task_id", "attempt_id", "worker_id"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("heartbeat requires task_id,attempt_id,worker_id")
    if not all(isinstance(value, str) and 1 <= len(value) <= 100
               for value in payload.values()):
        raise ValueError("invalid heartbeat fields")
    db.execute("BEGIN IMMEDIATE")
    row = db.execute("SELECT * FROM tasks WHERE task_id=?",
                     (payload["task_id"],)).fetchone()
    if not row:
        db.rollback()
        return 404, {"error": "task not found"}
    if (row["status"] != "RUNNING" or
        row["attempt_id"] != payload["attempt_id"] or
        row["worker_id"] != payload["worker_id"]):
        db.rollback()
        return 409, {"error": "heartbeat attempt mismatch or not running"}
    db.execute("UPDATE tasks SET updated_at=? WHERE task_id=?",
               (stamp(), payload["task_id"]))
    db.commit()
    return 200, {"ok": True, "task_id": payload["task_id"]}


def report(db, payload):
    required = {"task_id", "attempt_id", "worker_id", "status", "run_id",
                "result_text", "error_text"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("exact report fields required")
    if payload["status"] not in ("COMPLETED", "FAILED"):
        raise ValueError("status must be COMPLETED or FAILED")
    if not all(isinstance(payload[k], str) and len(payload[k]) <= size
               for k, size in (("task_id", 100), ("attempt_id", 100),
                               ("worker_id", 100), ("run_id", 128),
                               ("result_text", 50000), ("error_text", 5000))):
        raise ValueError("invalid report field size/type")
    db.execute("BEGIN IMMEDIATE")
    row = db.execute("SELECT * FROM tasks WHERE task_id=?",
                     (payload["task_id"],)).fetchone()
    if not row:
        db.rollback()
        return 404, {"error": "task not found"}
    if row["status"] != "RUNNING" or (
        row["attempt_id"] != payload["attempt_id"] or
        row["worker_id"] != payload["worker_id"]
    ):
        db.rollback()
        return 409, {"error": "attempt mismatch or task already closed"}
    at = stamp()
    db.execute("""UPDATE tasks SET status=?,run_id=?,result_text=?,
        error_text=?,updated_at=? WHERE task_id=?""",
        (payload["status"], payload["run_id"], payload["result_text"],
         payload["error_text"], at, payload["task_id"]))
    db.execute("INSERT INTO task_events(task_id,kind,at,note) VALUES(?,?,?,?)",
               (payload["task_id"], payload["status"], at, payload["worker_id"]))
    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE task_id=?",
                     (payload["task_id"],)).fetchone()
    return 200, {"task": public(row)}


class Handler(BaseHTTPRequestHandler):
    server_version = "CX-PAN-P1/0.1"

    def log_message(self, format_string, *args):
        # Only request path/response status; never log credentials or text payloads.
        pass

    def send_json(self, status, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        expected = TOKEN.read_text().strip()
        provided = self.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(
            provided, "Bearer " + expected
        )

    def handle_request(self, method):
        path = urlsplit(self.path).path
        if path == "/healthz" and method == "GET":
            return self.send_json(200, {"ok": True, "name": "cx-pan-p1"})
        if not self.authorized():
            return self.send_json(401, {"error": "unauthorized"})
        length = int(self.headers.get("Content-Length", "0"))
        if method == "POST" and not (0 < length <= MAX_BODY):
            return self.send_json(413, {"error": "invalid body length"})
        try:
            body = json.loads(self.rfile.read(length)) if method == "POST" else None
            db = connect()
            try:
                if method == "POST" and path == "/v1/tasks":
                    code, obj = enqueue(db, body)
                elif method == "POST" and path == "/v1/workers/claim":
                    code, obj = claim(db, body)
                elif method == "POST" and path == "/v1/workers/report":
                    code, obj = report(db, body)
                elif method == "POST" and path == "/v1/workers/heartbeat":
                    code, obj = heartbeat(db, body)
                elif method == "GET" and path.startswith("/v1/tasks/"):
                    parts = path.split("/")
                    if len(parts) not in (4, 5):
                        return self.send_json(404, {"error": "not found"})
                    task_id = parts[3]
                    row = db.execute(
                        "SELECT * FROM tasks WHERE task_id=?", (task_id,)
                    ).fetchone()
                    if row is None:
                        return self.send_json(404, {"error": "not found"})
                    link = db.execute(
                        "SELECT parent_task_id, source_sha256 FROM task_provenance "
                        "WHERE child_task_id=?", (task_id,)
                    ).fetchone()
                    provenance = dict(link) if link else None
                    if len(parts) == 5 and parts[4] == "result":
                        code, obj = 200, {
                            "task": public(row),
                            "result_text": row["result_text"],
                            "error_text": row["error_text"],
                            "provenance": provenance,
                        }
                    elif len(parts) == 4:
                        code, obj = 200, {
                            "task": public(row), "provenance": provenance
                        }
                    else:
                        code, obj = 404, {"error": "not found"}
                elif method == "GET" and path == "/v1/agents":
                    code, obj = 200, {"agents": [
                        {"id": key, "capability": val, "mode": "outbound_worker"}
                        for key, val in TARGETS.items()
                    ]}
                else:
                    code, obj = 404, {"error": "not found"}
            finally:
                db.close()
            return self.send_json(code, obj)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception:
            return self.send_json(500, {"error": "internal error"})

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18487)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "::1"):
        parser.error("P1 hub only supports loopback host")
    if not TOKEN.is_file() or not TOKEN.read_text().strip():
        parser.error("token file missing")
    with connect() as db:
        print("CX-PAN DB initialized", flush=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("CX-PAN hub listening on loopback", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
