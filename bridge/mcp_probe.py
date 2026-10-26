#!/usr/bin/env python3
"""Smoke-check a principal-scoped MCP streamable HTTP server.

Reads a single bearer token from stdin; never prints or persists it.
Only the safe echo target can be submitted by this smoke client.
"""
import argparse
import json
import sys
from pathlib import Path
import time
import urllib.error
import urllib.request


def invoke(base, token, method, params=None, request_id=1):
    msg = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        msg["params"] = params
    request = urllib.request.Request(
        base,
        method="POST",
        data=json.dumps(msg, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "MCP-Protocol-Version": "2025-11-25",
        },
    )
    with urllib.request.urlopen(request, timeout=13) as response:
        payload = response.read(180000).decode("utf-8")
    data = json.loads(payload)
    if "error" in data:
        raise RuntimeError("MCP JSON-RPC error: " + str(data["error"].get("code")))
    if data.get("result", {}).get("isError"):
        content = data["result"].get("content") or []
        raise RuntimeError("MCP tool error: " + str(content)[:350])
    return data["result"]


def output_dict(call_result):
    structured = call_result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    entries = call_result.get("content") or []
    for item in entries:
        if item.get("type") == "text":
            try:
                data = json.loads(item.get("text") or "")
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--client", choices=("chatgpt", "claude"), required=True)
    parser.add_argument("--submit-echo", action="store_true")
    parser.add_argument("--capture", choices=("README.md", "docs/SPEC.md", "docs/SCHEMAS.md"))
    parser.add_argument("--inspect-task")
    parser.add_argument("--read-local-token", action="store_true",
                        help="Use local CX-PAN connector credential file")
    args = parser.parse_args()
    if args.read_local_token:
        token = (Path.home()/".config/cx-pan/connectors"/
                 (args.client+".bearer")).read_text(encoding="utf-8").strip()
    else:
        token = sys.stdin.readline().strip()
    if len(token) < 40:
        parser.error("valid token required on stdin")
    base = args.url
    init = invoke(base, token, "initialize", {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": args.client+"-P7-test", "version": "1"},
    })
    print("MCP_INIT", args.client, init["protocolVersion"])
    listing = invoke(base, token, "tools/list", {}, request_id=2)
    names = [x["name"] for x in listing["tools"]]
    print("MCP_TOOLS", names)
    if not args.submit_echo and not args.capture and not args.inspect_task:
        return
    if args.submit_echo or args.capture:
        target = "repo.evidence.local" if args.capture else "echo.local"
        goal = args.capture or "P7 authorized " + args.client + " connector integration echo"
        key = ("p7-"+args.client+"-capture-"+goal.replace("/", "-").replace(".", "-")
               if args.capture else "p7-20261026-" + args.client + "-cloud-demo")
        res = invoke(base, token, "tools/call", {
            "name": "task_submit_safe",
            "arguments": {
                "target": target,
                "goal": goal,
                "idempotency_key": key,
            },
        }, request_id=3)
        data = output_dict(res)
        task_id = data.get("task_id")
        print("SUBMIT", data)
        if not task_id:
            raise RuntimeError("task submission returned no task ID")
    else:
        task_id = args.inspect_task
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        receipt = output_dict(invoke(base, token, "tools/call", {
            "name": "task_result", "arguments": {"task_id": task_id}
        }, request_id=4))
        status = receipt.get("status")
        if status in ("COMPLETED", "FAILED"):
            text = receipt.get("result_text") or ""
            summary = text[:140]
            if receipt.get("target") == "repo.evidence.local" and text:
                capsule = json.loads(text)
                summary = {k:capsule[k] for k in ("path","size_bytes","sha256")}
            print("TASK_FINAL", {"task_id": task_id, "status": status,
                                 "result": summary})
            return 0 if status == "COMPLETED" else 1
        time.sleep(4)
    raise RuntimeError("MCP task still pending; inspect task ID separately")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, ValueError) as exc:
        print("MCP_PROBE_FAILED:", exc, file=sys.stderr)
        sys.exit(1)
