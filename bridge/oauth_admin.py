#!/usr/bin/env python3
"""Owner-only OAuth administration, never mounted as an HTTP or MCP tool.

Audits and management output deliberately omit client secrets, OAuth request
secrets, authorization codes and access/refresh tokens. Runs via SSH only.
"""
import json
import re
import time
from datetime import datetime, timezone

from oauth_store import db_connect, digest

CLIENT_ID_RE = re.compile(r"^[0-9a-f-]{36}$", re.I)
MAX_RECENT_DCR = 5
DCR_WINDOW_SECONDS = 1800
MAX_PENDING_PER_CLIENT = 8
MAX_PENDING_GLOBAL = 30


def record_event(db, event, client_id=None, note=""):
    if event not in {
        "registration.open", "registration.close",
        "client.registered", "client.revoked",
        "owner.approved", "owner.denied",
    }:
        raise ValueError("unknown admin audit event")
    if not isinstance(note, str) or len(note) > 160:
        raise ValueError("invalid audit note")
    db.execute(
        "INSERT INTO audit_log(at,event,client_id,note) VALUES(?,?,?,?)",
        (int(time.time()), event, client_id, note)
    )


def client_metadata(client_id):
    db=db_connect()
    if db is None:
        return None
    try:
        row=db.execute(
            "SELECT client_id,client_json,created_at FROM clients WHERE client_id=?",
            (client_id,)
        ).fetchone()
        if row is None:
            return None
        parsed=json.loads(row["client_json"])
        return {
            "client_id":row["client_id"],
            "client_name":parsed.get("client_name"),
            "redirect_uris":parsed.get("redirect_uris") or [],
            "auth_method":parsed.get("token_endpoint_auth_method"),
            "scopes":parsed.get("scope"),
            "created_at":row["created_at"]
        }
    finally:
        db.close()


def registered_clients():
    db=db_connect()
    if db is None:
        return []
    try:
        items=db.execute(
            "SELECT client_id FROM clients ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    finally:
        db.close()
    return [client_metadata(row["client_id"]) for row in items]


def registration_capacity(db):
    now=int(time.time())
    recent=db.execute(
        "SELECT COUNT(*) FROM clients WHERE created_at>=?",
        (now-DCR_WINDOW_SECONDS,)
    ).fetchone()[0]
    return recent < MAX_RECENT_DCR


def pending_capacity(db, client_id):
    now=int(time.time())
    existing=db.execute(
        "SELECT COUNT(*) FROM pending WHERE client_id=? AND "
        "decision='pending' AND consumed=0 AND expires_at>?",
        (client_id,now)
    ).fetchone()[0]
    all_active=db.execute(
        "SELECT COUNT(*) FROM pending WHERE decision='pending' "
        "AND consumed=0 AND expires_at>?",(now,)
    ).fetchone()[0]
    return existing < MAX_PENDING_PER_CLIENT and all_active < MAX_PENDING_GLOBAL


def request_info(request_id):
    if not isinstance(request_id, str) or not (32 <= len(request_id) <= 128):
        raise ValueError("invalid owner request ID")
    db=db_connect()
    if db is None:
        return None
    try:
        row=db.execute(
            "SELECT client_id,scopes_json,redirect_uri,resource,"
            "expires_at,decision,consumed,request_digest "
            "FROM pending WHERE request_digest=?",
            (digest(request_id),)
        ).fetchone()
        if row is None:
            return None
        meta=client_metadata(row["client_id"]) or {}
        return {
            "request_sha256_prefix":row["request_digest"][:18],
            "client_id":row["client_id"],
            "client_name":meta.get("client_name"),
            "redirect_uri":row["redirect_uri"],
            "scopes":json.loads(row["scopes_json"]),
            "resource":row["resource"],
            "seconds_left":max(0,row["expires_at"]-int(time.time())),
            "decision":row["decision"],
            "consumed":bool(row["consumed"]),
        }
    finally:
        db.close()


def revoke_client(client_id):
    """Atomically invalidate client tokens/codes/pending grants and registration."""
    if not isinstance(client_id, str) or not CLIENT_ID_RE.fullmatch(client_id):
        raise ValueError("invalid registered client ID")
    db=db_connect(create=True)
    try:
        db.execute("BEGIN IMMEDIATE")
        exists=db.execute(
            "SELECT 1 FROM clients WHERE client_id=?",(client_id,)
        ).fetchone()
        if not exists:
            db.rollback()
            return False
        changed=db.execute(
            "UPDATE tokens SET revoked=1 WHERE client_id=? AND revoked=0",
            (client_id,)
        ).rowcount
        db.execute(
            "UPDATE codes SET redeemed=1 WHERE client_id=? AND redeemed=0",
            (client_id,)
        )
        db.execute(
            "UPDATE pending SET consumed=1,decision='denied' "
            "WHERE client_id=? AND consumed=0",(client_id,)
        )
        db.execute("DELETE FROM clients WHERE client_id=?",(client_id,))
        record_event(db,"client.revoked",client_id,
                     f"revoked_token_rows={changed}")
        db.commit()
        return True
    finally:
        db.close()


def recent_audit(limit=25):
    db=db_connect()
    if db is None:
        return []
    try:
        return [
            {"time":datetime.fromtimestamp(row["at"],timezone.utc).isoformat(),
             "event":row["event"],"client_id":row["client_id"],"note":row["note"]}
            for row in db.execute(
                "SELECT at,event,client_id,note FROM audit_log "
                "ORDER BY id DESC LIMIT ?",(min(max(limit,1),100),)
            ).fetchall()
        ]
    finally:
        db.close()
