#!/usr/bin/env python3
"""P8 owner-approved OAuth 2.1 authorization server for CX-PAN.

Uses the official Python MCP SDK routes for DCR, PKCE S256 token exchange,
refresh and revocation. Owner consent is enforced out of band using SSH CLI,
not a public password or unauthenticated consent button. OAuth codes/tokens
are 256-bit opaque secrets stored SHA-256-hashed in SQLite.

No credentials, client secrets or access tokens go to Git, Notion or stdout.
"""
import argparse
import html
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import uvicorn
from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider, AuthorizationParams,
    AuthorizationCode, RefreshToken, AccessToken, OAuthToken,
    TokenError, RegistrationError, AuthorizeError,
)
from mcp.server.auth.routes import (
    create_auth_routes, create_protected_resource_routes, build_metadata
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.routing import Route

from oauth_store import (
    OAUTH_DB, RESOURCE, ISSUER, SCOPE, PI_RESOURCE, PI_SCOPE, VALID_RESOURCE_SCOPES, MAX_AUTHORIZED_CLIENTS,
    digest, db_connect, registration_is_open, set_registration_window,
)
from oauth_admin import (
    record_event, registration_capacity, pending_capacity, request_info,
    registered_clients, client_metadata, revoke_client, recent_audit,
)

PENDING_AGE = 900
CODE_AGE = 300
ACCESS_AGE = 900
REFRESH_AGE = 30 * 24 * 3600
CHATGPT_CALLBACK = re.compile(
    r"^https://chatgpt\.com/connector/oauth/[a-zA-Z0-9_-]{6,150}$"
)
STABLE_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
OWNER_PAGE = ISSUER + "owner-approve"


def owner_callback_ok(url):
    return url == STABLE_CALLBACK or bool(CHATGPT_CALLBACK.fullmatch(url))


def _issue_pair(db, client_id, scopes, resource, family=None):
    now = int(time.time())
    family = family or secrets.token_hex(20)
    access = secrets.token_urlsafe(48)
    refresh = secrets.token_urlsafe(48)
    serialized = json.dumps(scopes, separators=(",", ":"))
    db.execute(
        "INSERT INTO tokens(token_digest,client_id,kind,scopes_json,resource,"
        "expires_at,family) VALUES(?,?,?,?,?,?,?)",
        (digest(access), client_id, "access", serialized, resource,
         now+ACCESS_AGE, family)
    )
    db.execute(
        "INSERT INTO tokens(token_digest,client_id,kind,scopes_json,resource,"
        "expires_at,family) VALUES(?,?,?,?,?,?,?)",
        (digest(refresh), client_id, "refresh", serialized, resource,
         now+REFRESH_AGE, family)
    )
    return OAuthToken(
        access_token=access, token_type="Bearer", expires_in=ACCESS_AGE,
        scope=" ".join(scopes), refresh_token=refresh,
    )


class OwnerApprovalOAuth(OAuthAuthorizationServerProvider[
    AuthorizationCode, RefreshToken, AccessToken
]):
    """The SDK validates redirect, client secret and S256 code verifier."""

    async def get_client(self, client_id):
        if not isinstance(client_id, str) or len(client_id) > 300:
            return None
        con=db_connect(create=True)
        try:
            row=con.execute(
                "SELECT client_json FROM clients WHERE client_id=?",
                (client_id,)
            ).fetchone()
            return (OAuthClientInformationFull.model_validate_json(
                row["client_json"]) if row else None)
        finally:
            con.close()

    async def register_client(self, client_info):
        # Owner controls when new OAuth clients may be registered. Existing
        # registered clients continue to work when the window is closed.
        if not registration_is_open():
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Owner has not opened a client enrollment window"
            )
        redirects = client_info.redirect_uris or []
        if not (1 <= len(redirects) <= 3) or not all(
            owner_callback_ok(str(u)) for u in redirects
        ):
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="Only verified ChatGPT connector callback URLs allowed",
            )
        if client_info.token_endpoint_auth_method not in (
            "none", "client_secret_post", "client_secret_basic"
        ):
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Unsupported token endpoint auth method",
            )
        if (client_info.scope.split() if client_info.scope else [SCOPE]) not in ([SCOPE],[PI_SCOPE]):
            raise RegistrationError(
                error="invalid_client_metadata", error_description="Scope denied"
            )
        if not client_info.client_id:
            raise RegistrationError(
                error="invalid_client_metadata", error_description="Missing client_id"
            )
        con=db_connect(create=True)
        try:
            con.execute("BEGIN IMMEDIATE")
            exists=con.execute(
                "SELECT 1 FROM clients WHERE client_id=?",
                (client_info.client_id,)
            ).fetchone()
            count=con.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            if not exists and (
                count>=MAX_AUTHORIZED_CLIENTS or not registration_capacity(con)
            ):
                con.rollback()
                raise RegistrationError(
                    error="invalid_client_metadata",
                    error_description="Client registration rate/quota exceeded"
                )
            con.execute(
                "INSERT OR IGNORE INTO clients(client_id,client_json,created_at)"
                " VALUES(?,?,?)",
                (client_info.client_id,
                 client_info.model_dump_json(exclude_none=True),
                 int(time.time()))
            )
            if not exists:
                record_event(con,"client.registered",client_info.client_id)
            con.commit()
        finally:
            con.close()

    async def authorize(self, client, params):
        if params.resource not in VALID_RESOURCE_SCOPES:
            raise AuthorizeError(
                error="invalid_request",
                error_description="Required resource audience does not match CX-PAN"
            )
        scopes=params.scopes or []
        if scopes != [VALID_RESOURCE_SCOPES[params.resource]]:
            raise AuthorizeError(
                error="invalid_scope",
                error_description="CX-PAN resource and requested scope do not match"
            )
        if not re.fullmatch(r"[a-zA-Z0-9_-]{43,128}", params.code_challenge):
            raise AuthorizeError(
                error="invalid_request", error_description="S256 PKCE required"
            )
        if not owner_callback_ok(str(params.redirect_uri)):
            raise AuthorizeError(
                error="invalid_request", error_description="Callback not allowed"
            )
        req=secrets.token_urlsafe(32)
        con=db_connect(create=True)
        try:
            con.execute("BEGIN IMMEDIATE")
            if not pending_capacity(con,client.client_id):
                con.rollback()
                raise AuthorizeError(
                    error="temporarily_unavailable",
                    error_description="Too many concurrent authorization requests"
                )
            con.execute(
                "INSERT INTO pending(request_digest,client_id,scopes_json,"
                "redirect_uri,redirect_explicit,code_challenge,state,resource,"
                "expires_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (digest(req),client.client_id,json.dumps(scopes),
                 str(params.redirect_uri),
                 1 if params.redirect_uri_provided_explicitly else 0,
                 params.code_challenge,params.state,params.resource,
                 int(time.time())+PENDING_AGE),
            )
            con.commit()
        finally:
            con.close()
        return OWNER_PAGE + "?" + urlencode({"request":req})

    async def load_authorization_code(self, client, authorization_code):
        con=db_connect()
        if not con:
            return None
        try:
            row=con.execute(
                "SELECT * FROM codes WHERE code_digest=? AND redeemed=0",
                (digest(authorization_code),),
            ).fetchone()
            if not row or row["client_id"]!=client.client_id or (
                row["expires_at"]<=int(time.time())
            ):
                return None
            return AuthorizationCode(
                code=authorization_code, client_id=row["client_id"],
                scopes=json.loads(row["scopes_json"]),
                expires_at=float(row["expires_at"]),
                code_challenge=row["code_challenge"],
                redirect_uri=row["redirect_uri"],
                redirect_uri_provided_explicitly=bool(row["redirect_explicit"]),
                resource=row["resource"],
            )
        finally:
            con.close()

    async def exchange_authorization_code(self, client, authorization_code):
        con=db_connect(create=True)
        try:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute(
                "SELECT * FROM codes WHERE code_digest=?",
                (digest(authorization_code.code),)
            ).fetchone()
            if not row or row["redeemed"] or row["client_id"]!=client.client_id or (
                row["expires_at"]<=int(time.time()) or
                row["resource"] not in VALID_RESOURCE_SCOPES
            ):
                con.rollback()
                raise TokenError(error="invalid_grant",
                                 error_description="Code missing, used or expired")
            con.execute(
                "UPDATE codes SET redeemed=1 WHERE code_digest=?",
                (digest(authorization_code.code),)
            )
            tokens=_issue_pair(con,client.client_id,json.loads(row["scopes_json"]),
                               row["resource"])
            con.commit()
            return tokens
        finally:
            con.close()

    async def load_refresh_token(self, client, refresh_token):
        con=db_connect()
        if not con:
            return None
        try:
            row=con.execute(
                "SELECT * FROM tokens WHERE token_digest=? AND kind='refresh'",
                (digest(refresh_token),)
            ).fetchone()
            if not row or row["revoked"] or row["client_id"]!=client.client_id or (
                row["expires_at"]<=int(time.time()) or row["resource"] not in VALID_RESOURCE_SCOPES
            ):
                return None
            return RefreshToken(
                token=refresh_token, client_id=client.client_id,
                scopes=json.loads(row["scopes_json"]),
                expires_at=row["expires_at"],
            )
        finally:
            con.close()

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        con=db_connect(create=True)
        try:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute(
                "SELECT * FROM tokens WHERE token_digest=? AND kind='refresh'",
                (digest(refresh_token.token),)
            ).fetchone()
            if not row or row["revoked"] or row["client_id"]!=client.client_id or (
                row["expires_at"]<=int(time.time()) or row["resource"] not in VALID_RESOURCE_SCOPES
            ):
                con.rollback()
                raise TokenError(error="invalid_grant",
                                 error_description="Refresh already rotated or expired")
            existing=json.loads(row["scopes_json"])
            if any(s not in existing for s in scopes) or not scopes:
                con.rollback()
                raise TokenError(error="invalid_scope",
                                 error_description="Refresh scope escalation denied")
            con.execute(
                "UPDATE tokens SET revoked=1 WHERE token_digest=?",
                (digest(refresh_token.token),)
            )
            result=_issue_pair(con,client.client_id,scopes,row["resource"],row["family"])
            con.commit()
            return result
        finally:
            con.close()

    async def load_access_token(self, token):
        con=db_connect()
        if con is None:
            return None
        try:
            row=con.execute(
                "SELECT * FROM tokens WHERE token_digest=? AND kind='access'",
                (digest(token),)
            ).fetchone()
            if not row or row["revoked"] or (
                row["expires_at"]<=int(time.time()) or row["resource"] not in VALID_RESOURCE_SCOPES
            ):
                return None
            return AccessToken(
                token=token, client_id=row["client_id"],
                scopes=json.loads(row["scopes_json"]),
                expires_at=row["expires_at"], resource=row["resource"]
            )
        finally:
            con.close()

    async def revoke_token(self, token):
        con=db_connect(create=True)
        try:
            row=con.execute(
                "SELECT family FROM tokens WHERE token_digest=?",
                (digest(token.token),)
            ).fetchone()
            if row:
                con.execute("UPDATE tokens SET revoked=1 WHERE family=?",
                            (row["family"],))
                con.commit()
        finally:
            con.close()


def owner_approve(request_id, verdict):
    """Only local SSH shell can execute this, not exposed as an HTTP POST."""
    if not isinstance(request_id, str) or len(request_id)<30:
        raise ValueError("Invalid pending request ID")
    con=db_connect(create=True)
    try:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute(
            "SELECT client_id,decision,expires_at,consumed FROM pending WHERE request_digest=?",
            (digest(request_id),)
        ).fetchone()
        if (not row or row["decision"]!="pending" or row["consumed"]
                or row["expires_at"]<=int(time.time())):
            con.rollback()
            raise ValueError("Request absent, already decided or expired")
        con.execute("UPDATE pending SET decision=? WHERE request_digest=?",
                    (verdict,digest(request_id)))
        record_event(con,"owner.approved" if verdict=="approved" else "owner.denied",
                     row["client_id"],"request_hash_prefix="+digest(request_id)[:18])
        con.commit()
        return True
    finally:
        con.close()


async def pending_page(request):
    q=request.query_params.get("request","")
    if not isinstance(q,str) or not (30<=len(q)<=128):
        return JSONResponse({"error":"pending request not found"},status_code=404)
    con=db_connect()
    try:
        row=con.execute(
            "SELECT * FROM pending WHERE request_digest=?", (digest(q),)
        ).fetchone() if con else None
        if not row or row["expires_at"]<=int(time.time()):
            return HTMLResponse("This authorization request expired.",status_code=410)
        if row["consumed"]:
            return HTMLResponse("This authorization request has already completed.",
                                status_code=410)
        if row["decision"]=="approved":
            code=secrets.token_urlsafe(40)
            con.execute("BEGIN IMMEDIATE")
            updated=con.execute(
                "UPDATE pending SET consumed=1 WHERE request_digest=? "
                "AND consumed=0 AND decision='approved' AND expires_at>?",
                (digest(q),int(time.time()))
            )
            if updated.rowcount!=1:
                con.rollback()
                return HTMLResponse("This request was already completed.",
                                    status_code=409)
            con.execute(
                "INSERT INTO codes(code_digest,client_id,scopes_json,redirect_uri,"
                "redirect_explicit,code_challenge,resource,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (digest(code),row["client_id"],row["scopes_json"],
                 row["redirect_uri"],row["redirect_explicit"],
                 row["code_challenge"],row["resource"],int(time.time())+CODE_AGE)
            )
            con.commit()
            payload={"code":code}
            if row["state"]:
                payload["state"]=row["state"]
            callback=row["redirect_uri"]
            separator="&" if "?" in callback else "?"
            return RedirectResponse(callback+separator+urlencode(payload),
                                    status_code=302,
                                    headers={"Cache-Control":"no-store",
                                             "Referrer-Policy":"no-referrer"})
        if row["decision"]=="denied":
            con.execute("UPDATE pending SET consumed=1 WHERE request_digest=?",
                        (digest(q),))
            con.commit()
            payload={"error":"access_denied"}
            if row["state"]:
                payload["state"]=row["state"]
            return RedirectResponse(
                row["redirect_uri"]+"?"+urlencode(payload),
                status_code=302,
                headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})
        cid=row["client_id"]
        c=con.execute("SELECT client_json FROM clients WHERE client_id=?",
                      (cid,)).fetchone()
        client=json.loads(c["client_json"]) if c else {}
        name=html.escape((client.get("client_name") or "ChatGPT connection")[:120])
        callback=html.escape(row["redirect_uri"])
        remaining=max(0,int(row["expires_at"]-time.time()))
        selected_scopes=json.loads(row["scopes_json"])
        if selected_scopes==[PI_SCOPE] and row["resource"]==PI_RESOURCE:
            scope_description=(
                "tasks:pi_text: up to 6 new MiniMax-M2.7 text-only model "
                "tasks per UTC day through the owner's xinhailin Pi agent. "
                "This may use paid/token-plan model allowance. The Pi "
                "runtime cannot read or edit files, run shell commands, "
                "call MCP tools, or save sessions through this endpoint."
            )
        elif selected_scopes==[SCOPE] and row["resource"]==RESOURCE:
            scope_description=(
                "tasks:safe: safe echo and approved public-document "
                "capture. It cannot run shell commands, access NAS/private "
                "files, or invoke paid models."
            )
        else:
            return HTMLResponse("Unsupported OAuth scope/resource",status_code=400)
        # Request ID is shown only to the human who opened the OAuth browser.
        safe_code=html.escape(q)
        page=f"""<!doctype html><html lang="en">
<meta charset="utf-8"><meta http-equiv="refresh" content="5">
<meta name="referrer" content="no-referrer">
<title>CX-PAN connection approval</title>
<style>body{{font:16px system-ui,sans-serif;max-width:640px;
margin:50px auto;padding:20px;line-height:1.6}}</style>
<h2>CX-PAN — pending owner approval</h2>
<p>The client <b>{name}</b> requests the following explicitly
approved permission: {html.escape(scope_description)}</p>
<p>Requested ChatGPT redirect: <code>{callback}</code></p>
<p>To approve, the CX-PAN owner must inspect and approve this one-time
request from an authenticated SSH terminal, not from a public web form.</p>
<p>Request ID: <code>{safe_code}</code></p>
<p>Seconds until expiry: {remaining}. This page automatically refreshes.
Do not approve unexpected requests.</p></html>"""
        return HTMLResponse(page,headers={
            "Cache-Control":"no-store",
            "Referrer-Policy":"no-referrer",
            "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'",
        })
    finally:
        if con:
            con.close()


async def metadata_with_public_client_methods(_request):
    """Describe the public PKCE DCR client method supported by this server.

    MCP SDK 1.26 builds AS metadata with only client_secret_{post,basic}
    despite TokenHandler also supporting registered public DCR clients
    (token_endpoint_auth_method=none). Explicitly advertise that actual
    tested method without changing SDK token validation.
    """
    metadata=build_metadata(
        AnyHttpUrl(ISSUER),None,
        ClientRegistrationOptions(
            enabled=True, valid_scopes=[SCOPE,PI_SCOPE], default_scopes=[SCOPE]
        ),
        RevocationOptions(enabled=True),
    )
    methods=list(metadata.token_endpoint_auth_methods_supported or [])
    metadata.token_endpoint_auth_methods_supported=[
        "none", *[m for m in methods if m!="none"]
    ]
    return JSONResponse(metadata.model_dump(mode="json",exclude_none=True),
                        headers={"Cache-Control":"no-store"})


def create_app():
    provider=OwnerApprovalOAuth()
    issuer=AnyHttpUrl(ISSUER)
    routes=create_auth_routes(
        provider,issuer,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,valid_scopes=[SCOPE,PI_SCOPE],default_scopes=[SCOPE]
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    routes=[
        Route("/.well-known/oauth-authorization-server",
              metadata_with_public_client_methods,methods=["GET","OPTIONS"])
        if route.path=="/.well-known/oauth-authorization-server"
        else route for route in routes
    ]
    routes += create_protected_resource_routes(
        AnyHttpUrl(RESOURCE),[issuer],scopes_supported=[SCOPE],
        resource_name="CX-PAN restricted safe tasks",
    )
    routes += create_protected_resource_routes(
        AnyHttpUrl(PI_RESOURCE),[issuer],scopes_supported=[PI_SCOPE],
        resource_name="CX-PAN xinhailin Pi text only tasks",
    )
    routes += [Route("/owner-approve",pending_page,methods=["GET"])]
    return Starlette(routes=routes)


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("serve")
    owner=sub.add_parser("owner")
    owner_sub=owner.add_subparsers(dest="op",required=True)
    owner_sub.add_parser("list")
    owner_sub.add_parser("clients")
    owner_sub.add_parser("audit")
    request_info_arg=owner_sub.add_parser("request-info")
    request_info_arg.add_argument("request_id")
    revoke_arg=owner_sub.add_parser("revoke-client")
    revoke_arg.add_argument("client_id")
    win=owner_sub.add_parser("registration-open")
    win.add_argument("--minutes",type=int,default=10)
    owner_sub.add_parser("registration-close")
    for name in ("approve","deny"):
        x=owner_sub.add_parser(name)
        x.add_argument("request_id")
    args=parser.parse_args()
    if args.action=="owner":
        if args.op=="registration-open":
            if not (1 <= args.minutes <= 30):
                parser.error("enrollment window must be 1..30 minutes")
            set_registration_window(args.minutes*60)
            with db_connect(create=True) as con:
                record_event(con,"registration.open",note=f"minutes={args.minutes}")
                con.commit()
            print("OAuth DCR enrollment window opened for",args.minutes,"minutes.")
            return 0
        if args.op=="registration-close":
            set_registration_window(0)
            with db_connect(create=True) as con:
                record_event(con,"registration.close")
                con.commit()
            print("OAuth DCR enrollment window closed.")
            return 0
        if args.op=="clients":
            print(json.dumps(registered_clients(),ensure_ascii=False,indent=2))
            return 0
        if args.op=="audit":
            print(json.dumps(recent_audit(),ensure_ascii=False,indent=2))
            return 0
        if args.op=="request-info":
            info=request_info(args.request_id)
            if info is None:
                print("Request not found")
                return 1
            print(json.dumps(info,ensure_ascii=False,indent=2))
            return 0
        if args.op=="revoke-client":
            if not revoke_client(args.client_id):
                print("Client not found")
                return 1
            print("Client disabled and its tokens/codes/pending grants invalidated.")
            return 0
        if args.op=="list":
            print("OAuth DCR enrollment currently", "OPEN" if registration_is_open() else "CLOSED")
            con=db_connect(create=True)
            try:
                rows=con.execute(
                    "SELECT request_digest,client_id,redirect_uri,resource,"
                    "expires_at FROM pending WHERE decision='pending' AND "
                    "consumed=0 AND expires_at>? ORDER BY expires_at",
                    (int(time.time()),)
                ).fetchall()
                print("Pending CX-PAN OAuth owner approvals:",len(rows))
                for r in rows:
                    print("request_sha256_prefix",r["request_digest"][:18],
                          "redirect",r["redirect_uri"],
                          "seconds_left",r["expires_at"]-int(time.time()))
            finally:
                con.close()
            return 0
        owner_approve(args.request_id,"approved" if args.op=="approve" else "denied")
        print("Owner decision applied (no tokens displayed).")
        return 0
    db=db_connect(create=True)
    db.close()
    uvicorn.run(create_app(),host="127.0.0.1",
                port=int(os.getenv("CX_PAN_OAUTH_PORT","18489")),
                log_level="warning",access_log=False)
    return 0


if __name__=="__main__":
    sys.exit(main())
