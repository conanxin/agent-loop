#!/usr/bin/env python3
"""P8 one-time synthetic OAuth HTTPS integration check, privileged CLI only.

Not invoked from an HTTP endpoint, MCP client, service, or model tool.
Creates one synthetic DCR client and owner-approves ONLY its unique request.
Revokes every issued token before exit; never logs access/refresh/client secrets.
"""
import base64
import hashlib
import os
import secrets
import sys
import time
from urllib.parse import parse_qs, urlparse

import httpx
from oauth_server import owner_approve
from oauth_store import set_registration_window
from oauth_admin import revoke_client

ORIGIN="https://www.conanxin.com"
RESOURCE=ORIGIN+"/cxpan/chatgpt/mcp"
CALLBACK="https://chatgpt.com/connector/oauth/cxpan-p8-synthetic-test-20261027"

def unwrap(result):
    body=result.json()
    if body.get("error"):
        raise RuntimeError("JSON-RPC returned error code "+str(body["error"].get("code")))
    res=body.get("result") or {}
    if res.get("isError"):
        raise RuntimeError("MCP tool rejected safe synthetic request")
    if isinstance(res.get("structuredContent"),dict):
        return res["structuredContent"]
    for x in res.get("content",[]):
        if x.get("type")=="text":
            import json
            d=json.loads(x["text"])
            if isinstance(d,dict):return d
    return res

def main():
    if os.getenv("CX_PAN_TEST_OWNER_EXPLICIT","")!="YES":
        raise RuntimeError("Synthetic OAuth test owner approval must be explicit")
    # Synthetic client is the only purpose of this short window. The
    # operator should close it after the test even if a network step fails.
    set_registration_window(300)
    c=httpx.Client(base_url=ORIGIN,follow_redirects=False,timeout=13)
    response=c.get("/.well-known/oauth-authorization-server")
    response.raise_for_status()
    assert "S256" in response.json()["code_challenge_methods_supported"]
    response=c.get("/.well-known/oauth-protected-resource/cxpan/chatgpt/mcp")
    response.raise_for_status()
    assert response.json()["resource"]==RESOURCE
    reg=c.post("/register",json={
        "redirect_uris":[CALLBACK],
        "token_endpoint_auth_method":"client_secret_post",
        "grant_types":["authorization_code","refresh_token"],
        "response_types":["code"],
        "scope":"tasks:safe",
        "client_name":"CX-PAN synthetic security test (no real ChatGPT account)",
    })
    reg.raise_for_status()
    data=reg.json()
    cid,secret=data["client_id"],data["client_secret"]
    verifier=secrets.token_urlsafe(44)
    challenge=base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    status=c.get("/authorize",params={
        "response_type":"code","client_id":cid,
        "redirect_uri":CALLBACK,"code_challenge":challenge,
        "code_challenge_method":"S256",
        "scope":"tasks:safe","resource":RESOURCE,
        "state":"cxpan-p8-synthetic-state",
    })
    assert status.status_code==302
    q=urlparse(status.headers["location"])
    assert q.path=="/owner-approve"
    request_id=parse_qs(q.query)["request"][0]
    pending=c.get("/owner-approve",params={"request":request_id})
    assert pending.status_code==200
    assert "pending owner approval" in pending.text
    print("SYNTHETIC_DCR_AND_OWNER_PENDING_PASS",flush=True)
    # Only a trusted on-host operator can call this function. No remote
    # endpoint accepts approval POST and no true ChatGPT link is approved.
    owner_approve(request_id,"approved")
    callback=c.get("/owner-approve",params={"request":request_id})
    assert callback.status_code==302
    u=urlparse(callback.headers["location"])
    assert callback.headers["location"].startswith(CALLBACK+"?")
    vals=parse_qs(u.query)
    assert vals["state"]==["cxpan-p8-synthetic-state"]
    code=vals["code"][0]
    t=c.post("/token",data={
        "grant_type":"authorization_code", "client_id":cid,
        "client_secret":secret,"code":code,
        "code_verifier":verifier,"redirect_uri":CALLBACK,
        "resource":RESOURCE,
    })
    t.raise_for_status()
    token=t.json()
    access=token["access_token"]
    refresh=token["refresh_token"]
    # Token remains in process memory, never persisted or printed.
    headers={
        "Authorization":"Bearer "+access,
        "Accept":"application/json, text/event-stream",
        "Content-Type":"application/json",
    }
    init=c.post("/cxpan/chatgpt/mcp",json={
        "jsonrpc":"2.0","id":1,"method":"initialize","params":{
            "protocolVersion":"2025-11-25","capabilities":{},
            "clientInfo":{"name":"P8 synthetic probe","version":"1"}
        }
    },headers=headers)
    assert init.status_code==200, init.status_code
    print("SYNTHETIC_OAUTH_ACCESS_MCP_INIT_PASS",flush=True)
    wrong=c.post("/cxpan/claude/mcp",json={
        "jsonrpc":"2.0","id":2,"method":"tools/list","params":{}
    },headers=headers)
    assert wrong.status_code==401
    tools=c.post("/cxpan/chatgpt/mcp",json={
        "jsonrpc":"2.0","id":3,"method":"tools/list","params":{}
    },headers=headers)
    assert tools.status_code==200
    names=[x["name"] for x in tools.json()["result"]["tools"]]
    assert set(names)=={"agents_list","task_get","task_result","task_submit_safe"}
    key="p8-synthetic-owner-tested-20261027"
    task=unwrap(c.post("/cxpan/chatgpt/mcp",json={
        "jsonrpc":"2.0","id":4,"method":"tools/call",
        "params":{"name":"task_submit_safe","arguments":{
            "target":"echo.local",
            "goal":"Synthetic OAuth-safe echo integration",
            "idempotency_key":key
        }}
    },headers=headers))
    task_id=task["task_id"]
    deadline=time.monotonic()+75
    while time.monotonic()<deadline:
        res=unwrap(c.post("/cxpan/chatgpt/mcp",json={
            "jsonrpc":"2.0","id":5,"method":"tools/call",
            "params":{"name":"task_result","arguments":{"task_id":task_id}}
        },headers=headers))
        if res["status"]=="COMPLETED":
            assert (res.get("result_text") or "").startswith("ECHO_OK")
            print("SYNTHETIC_OAUTH_SAFE_TASK_COMPLETED",flush=True)
            break
        time.sleep(4)
    else:
        raise RuntimeError("Synthetic echo did not finish")
    rotate=c.post("/token",data={
        "grant_type":"refresh_token","client_id":cid,
        "client_secret":secret,"refresh_token":refresh,
        "scope":"tasks:safe",
    })
    rotate.raise_for_status()
    pair=rotate.json()
    refreshed=pair["access_token"]
    print("SYNTHETIC_OAUTH_REFRESH_PASS",flush=True)
    # Revocation of one token revokes the whole family in server SQLite.
    revoke=c.post("/revoke",data={
        "client_id":cid,"client_secret":secret,
        "token":pair["refresh_token"],
        "token_type_hint":"refresh_token",
    })
    assert revoke.status_code==200, revoke.status_code
    blocked=c.post("/cxpan/chatgpt/mcp",json={
        "jsonrpc":"2.0","id":6,"method":"tools/list","params":{}
    },headers={**headers,"Authorization":"Bearer "+refreshed})
    assert blocked.status_code==401
    print("SYNTHETIC_OAUTH_REVOCATION_PASS",flush=True)
    assert revoke_client(cid), "synthetic client should be removed from owner registry"
    print("SYNTHETIC_DCR_CLIENT_REMOVED",flush=True)
    set_registration_window(0)
    print("SYNTHETIC_DCR_REGISTRATION_WINDOW_CLOSED",flush=True)
    print("SYNTHETIC_OAUTH_ONLY_NO_NATIVE_CHATGPT_ACCOUNT_CONNECTED",flush=True)
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("P9_SYNTHETIC_CHECK_FAILED",type(exc).__name__,
              str(exc)[:150] if not isinstance(exc,httpx.HTTPStatusError) else
              f"HTTP_{exc.response.status_code}",file=sys.stderr)
        sys.exit(1)
    finally:
        # A failed synthetic probe must never leave DCR enrollment open.
        try:
            set_registration_window(0)
        except Exception:
            pass
