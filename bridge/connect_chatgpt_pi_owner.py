#!/usr/bin/env python3
"""Interactive owner-only ChatGPT MCP plugin connection assistant.

Run in a *real* cloud SSH or Tencent browser console terminal with a TTY. Not callable by CX-PAN MCP.
Never accepts approval over ChatGPT messages or redirects.
Never prints/records OAuth Request ID, client secret, or access token.
"""
import argparse
import json
from getpass import getpass
import re
import subprocess
import sys
from urllib.parse import urlparse

CLI="/home/ubuntu/cx-pan-hub/oauth_server.py"
REMOTE_PY="python3"
SSH_ALIAS="tencent"
PRIVATE_PLUGIN="https://chatgpt.com/plugins"
PUBLIC_OAUTH_RESOURCE="https://www.conanxin.com/cxpan/chatgpt-pi/mcp"
TOKEN_RE=re.compile(r"^[A-Za-z0-9_-]{40,128}$")
CALLBACK_RE=re.compile(r"^https://chatgpt\.com/connector/oauth/[A-Za-z0-9_-]{6,150}$")
STABLE_CALLBACK="https://chatgpt.com/connector_platform_oauth_redirect"


def ssh_owner(*args):
    """Perform server-local owner command; keep sensitive Request ID out of ChatGPT."""
    proc=subprocess.run(
        [sys.executable,CLI,"owner",*args],
        capture_output=True,text=True,timeout=16,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode!=0:
        raise RuntimeError("Trusted local owner command failed; consult terminal logs")
    return proc.stdout.strip()


def validate_request_id(value):
    if not isinstance(value,str) or not TOKEN_RE.fullmatch(value):
        raise ValueError("Request ID must be an unmodified 40–128 char URL-safe code")
    return value


def verify_owner_view(view):
    """Fail closed if server reports unexpected OAuth permission or redirect."""
    if not isinstance(view,dict):
        raise ValueError("Owner request details must be a JSON object")
    redirect=view.get("redirect_uri","")
    correct_callback=(redirect==STABLE_CALLBACK or
                      bool(CALLBACK_RE.fullmatch(redirect)))
    if not correct_callback:
        raise ValueError("Request redirect is not an allowed ChatGPT callback")
    if view.get("scopes")!=["tasks:pi_text"]:
        raise ValueError("Request exceeds the safe MCP scope")
    if view.get("resource")!=PUBLIC_OAUTH_RESOURCE:
        raise ValueError("Request resource mismatch")
    if view.get("decision")!="pending" or view.get("consumed"):
        raise ValueError("Request is already decided or consumed")
    if not (0<int(view.get("seconds_left",0))<=900):
        raise ValueError("Request expired or has abnormal lifetime")
    return {
        "client_name":str(view.get("client_name") or "Unknown")[:120],
        "client_id":str(view.get("client_id") or "")[:80],
        "redirect_uri":redirect,
        "scopes":view["scopes"],
        "resource":view["resource"],
        "seconds_left":view["seconds_left"],
        "request_sha256_prefix":view.get("request_sha256_prefix"),
    }


def main():
    parser=argparse.ArgumentParser(
        description="Owner-interactive CX-PAN Pi TEXT-only plugin OAuth connection"
    )
    parser.add_argument("--check-only",action="store_true",
                        help="Read registration/client state without opening OAuth")
    args=parser.parse_args()
    if args.check_only:
        print(ssh_owner("list"))
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("P9 onboarding needs a real interactive TTY, not an agent/pipe.",
              file=sys.stderr)
        return 2
    print("CX-PAN PI TEXT MCP URL:",PUBLIC_OAUTH_RESOURCE,flush=True)
    print("This does NOT install a plugin. Connect a SEPARATE custom MCP server first.")
    print("NOTICE: tasks:pi_text can consume MiniMax model allowance, maximum 6 new tasks per day.")
    print("Open ChatGPT WEB in your own browser and start the OAuth connection.")
    print("Registration opens for up to 10 minutes. Approval must be YOUR decision.")
    confirmed=input("Type START to open a temporary registration window: ").strip()
    if confirmed!="START":
        print("No registration window opened.")
        return 1
    try:
        print(ssh_owner("registration-open","--minutes","10"))
        print("Open the plugin above; inspect the OAuth request in your browser.")
        request_id=validate_request_id(getpass(
            "Paste the one-time Request ID (input hidden): "
        ).strip())
        view=verify_owner_view(json.loads(
            ssh_owner("request-info",request_id)
        ))
        print("\nREVIEW YOUR REQUEST BEFORE APPROVAL:")
        for key,val in view.items():
            print(f" {key}: {val}")
        response=input(
            "\nType APPROVE only if you initiated this OAuth request: "
        ).strip()
        if response!="APPROVE":
            print("Approval declined. Unapproved request will expire.")
            return 1
        print(ssh_owner("approve",request_id))
        print("Owner approval recorded; complete ChatGPT browser redirect.")
        print("After linking, invoke CX-PAN agents_list then a safe Echo task.")
        return 0
    finally:
        # Closing registration does not invalidate an already registered OAuth
        # client or a pending grant. It just prevents new DCR enrollments.
        try:
            print(ssh_owner("registration-close"))
        except Exception:
            print("WARNING: verify DCR registration is closed over trusted SSH.",
                  file=sys.stderr)


if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,RuntimeError,subprocess.TimeoutExpired,
            json.JSONDecodeError) as exc:
        # Never include the user-entered request ID in an error message.
        print("CX-PAN connection stopped:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
