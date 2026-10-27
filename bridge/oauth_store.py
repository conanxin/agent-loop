#!/usr/bin/env python3
"""P8 shared OAuth token store: SQLite, opaque SHA-256 token hashes, fixed audience.

Both issuer (18489) and existing private MCP resource server (18488) run
on the same Tencent host/user. No access tokens are persisted in plaintext.
"""
import hashlib
import os
import sqlite3
import time
from pathlib import Path

OAUTH_DB = Path(os.getenv(
    "CX_PAN_OAUTH_DB", str(Path.home() / ".local/share/cx-pan/oauth.sqlite3")))
RESOURCE = "https://www.conanxin.com/cxpan/chatgpt/mcp"
ISSUER = "https://www.conanxin.com/"
SCOPE = "tasks:safe"
MAX_AUTHORIZED_CLIENTS = 40


def digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def db_connect(create=False):
    if not OAUTH_DB.exists() and not create:
        return None
    if create:
        OAUTH_DB.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(OAUTH_DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    if create:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS clients(
            client_id TEXT PRIMARY KEY,
            client_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending(
            request_digest TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            redirect_explicit INTEGER NOT NULL,
            code_challenge TEXT NOT NULL,
            state TEXT,
            resource TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            decision TEXT NOT NULL DEFAULT 'pending',
            consumed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS codes(
            code_digest TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            redirect_uri TEXT NOT NULL,
            redirect_explicit INTEGER NOT NULL,
            code_challenge TEXT NOT NULL,
            resource TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            redeemed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tokens(
            token_digest TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            resource TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            family TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS oauth_token_family ON tokens(family);
        CREATE TABLE IF NOT EXISTS config(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        os.chmod(OAUTH_DB, 0o600)
    return db


def verify_access(token, resource=RESOURCE, scope=SCOPE):
    """Fail closed. Never return the token or unfiltered database records."""
    if not isinstance(token, str) or not (35 <= len(token) <= 256):
        return False
    con = db_connect()
    if con is None:
        return False
    try:
        row = con.execute("""
            SELECT scopes_json, resource, expires_at, revoked, kind
            FROM tokens WHERE token_digest=?
        """, (digest(token),)).fetchone()
        if not row or row["kind"] != "access" or row["revoked"]:
            return False
        if row["resource"] != resource or row["expires_at"] <= int(time.time()):
            return False
        import json
        return scope in json.loads(row["scopes_json"])
    except (sqlite3.DatabaseError, ValueError):
        return False
    finally:
        con.close()


def set_registration_window(seconds):
    """Only an authenticated on-host owner CLI can call this function."""
    if not isinstance(seconds, int) or not (0 <= seconds <= 1800):
        raise ValueError("registration window must be between 0 and 1800 seconds")
    until=int(time.time())+seconds if seconds else 0
    with db_connect(create=True) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO config(key,value) VALUES('registration_open_until',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(until),)
        )
        db.commit()
    return until


def registration_is_open():
    con=db_connect(create=True)
    try:
        row=con.execute(
            "SELECT value FROM config WHERE key='registration_open_until'"
        ).fetchone()
        return bool(row and int(row["value"])>int(time.time()))
    except (sqlite3.DatabaseError,ValueError):
        return False
    finally:
        con.close()
