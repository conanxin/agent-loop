#!/usr/bin/env python3
"""CX-PAN P1 CLI. Uses authorized local SSH forward to the cloud loopback hub."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE_URL = os.getenv("CX_PAN_URL", "http://127.0.0.1:18487").rstrip("/")
TOKEN_PATH = Path(os.getenv("CX_PAN_TOKEN_FILE",
                            str(Path.home() / ".config/cx-pan/token")))


def request_json(method, path, payload=None):
    token = TOKEN_PATH.read_text().strip()
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE_URL + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            error = exc.read().decode("utf-8")[:2000]
        except Exception:
            error = "unreadable error"
        raise RuntimeError(f"HTTP {exc.code}: {error}") from exc


def main():
    parser = argparse.ArgumentParser(description="CX-PAN P1 task client")
    sub = parser.add_subparsers(dest="op", required=True)

    submit = sub.add_parser("submit", help="Create an echo or read-only Claude Code task")
    submit.add_argument("--target", choices=(
        "echo.local", "claude.code.local", "hermes.health.local",
        "openclaw.health.local", "repo.validate.local",
        "hermes.model.local"
    ), required=True)
    submit.add_argument("--goal", required=True)
    submit.add_argument("--idempotency-key",
                        help="Stable key; omit to generate a unique key")
    submit.add_argument("--project-id", default="CX-PAN")
    submit.add_argument("--requester", default="chatgpt.cxre")

    status = sub.add_parser("status")
    status.add_argument("task_id")
    result = sub.add_parser("result")
    result.add_argument("task_id")
    sub.add_parser("agents")

    args = parser.parse_args()
    if args.op == "submit":
        target = args.target
        data = {
            "idempotency_key": args.idempotency_key or str(uuid.uuid4()),
            "requester": args.requester,
            "project_id": args.project_id,
            "target": target,
            "capability": (
                "repo.inspect" if target == "claude.code.local"
                else "repo.validate" if target == "repo.validate.local"
                else "gateway.health" if target.endswith(".health.local")
                else "text.review" if target == "hermes.model.local" else "echo"
            ),
            "goal": args.goal,
            "repo_id": (
                "agent-loop" if target in ("claude.code.local", "repo.validate.local")
                else "none"
            ),
        }
        output = request_json("POST", "/v1/tasks", data)
    elif args.op == "agents":
        output = request_json("GET", "/v1/agents")
    else:
        output = request_json(
            "GET", f"/v1/tasks/{args.task_id}" +
            ("/result" if args.op == "result" else "")
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ConnectionError, OSError) as exc:
        print(f"CX-PAN: {exc}", file=sys.stderr)
        sys.exit(1)
