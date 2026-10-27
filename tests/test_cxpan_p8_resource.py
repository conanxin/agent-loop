#!/usr/bin/env python3
"""P8 resource-server OAuth audience and scope enforcement regression.

Offline TestClient calls with temporary SQLite files and credentials only.
"""
import hashlib
import json
import secrets
import sys
import tempfile
import time
import unittest
from pathlib import Path

from starlette.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"bridge"))
import oauth_store
import mcp_gateway


class ResourceServerOAuthTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.old_db,self.old_clients,self.old_quota=(
            oauth_store.OAUTH_DB,mcp_gateway.CLIENTS,mcp_gateway.QUOTA_DB
        )
        oauth_store.OAUTH_DB=root/"oauth.sqlite3"
        mcp_gateway.CLIENTS=root/"clients.json"
        mcp_gateway.QUOTA_DB=root/"quota.sqlite3"
        self.addCleanup(self.restore)
        mcp_gateway.CLIENTS.write_text(json.dumps({
            "chatgpt":hashlib.sha256(b"legacy-only-chatgpt").hexdigest(),
            "claude":hashlib.sha256(b"legacy-only-claude").hexdigest(),
        }))
        self.token=secrets.token_urlsafe(48)
        self.write_token()
        self.client=TestClient(mcp_gateway.create_app(),
                               base_url="http://127.0.0.1:18488")
        self.client.__enter__()
        self.addCleanup(lambda:self.client.__exit__(None,None,None))

    def restore(self):
        (oauth_store.OAUTH_DB,mcp_gateway.CLIENTS,mcp_gateway.QUOTA_DB)=(
            self.old_db,self.old_clients,self.old_quota
        )

    def write_token(self,resource=oauth_store.RESOURCE,scopes=None,expires=700):
        scopes = scopes if scopes is not None else [oauth_store.SCOPE]
        with oauth_store.db_connect(create=True) as db:
            db.execute(
                "INSERT OR REPLACE INTO tokens"
                "(token_digest,client_id,kind,scopes_json,resource,"
                "expires_at,family,revoked) VALUES(?,?,?,?,?,?,?,0)",
                (oauth_store.digest(self.token),"chatgpt-p8-client","access",
                 json.dumps(scopes),resource,int(time.time())+expires,"p8-test-family")
            )
            db.commit()

    def probe(self,endpoint,token=None):
        hdr={
            "Accept":"application/json, text/event-stream",
            "Authorization":"Bearer " + (token or self.token)
        }
        return self.client.post(endpoint,json={
            "jsonrpc":"2.0","id":1,"method":"initialize",
            "params":{"protocolVersion":"2025-11-25",
                      "capabilities":{},
                      "clientInfo":{"name":"OAuth-safe test","version":"1"}}
        },headers=hdr)

    def test_oauth_token_works_for_chatgpt_only(self):
        r=self.probe("/chatgpt/mcp")
        self.assertEqual(r.status_code,200,r.text[:380])
        self.assertEqual(
            r.json()["result"]["protocolVersion"],"2025-11-25"
        )
        cross=self.probe("/claude/mcp")
        self.assertEqual(cross.status_code,401)
        self.assertEqual(
            self.probe("/chatgpt/mcp",token="unknown-invalid-token").status_code,401
        )

    def test_invalid_audience_expiry_scope_and_revocation_all_challenge(self):
        for kwargs in (
            {"resource":"https://evil.example/private"},
            {"expires":-5},
            {"scopes":["other:scope"]},
        ):
            self.write_token(**kwargs)
            r=self.probe("/chatgpt/mcp")
            self.assertEqual(r.status_code,401)
            auth=r.headers.get("www-authenticate","")
            self.assertIn("oauth-protected-resource",auth)
            self.assertIn('scope="tasks:safe"',auth)
        self.write_token()
        with oauth_store.db_connect() as db:
            db.execute("UPDATE tokens SET revoked=1 WHERE token_digest=?",
                       (oauth_store.digest(self.token),))
            db.commit()
        self.assertEqual(self.probe("/chatgpt/mcp").status_code,401)

    def test_caller_cannot_use_oauth_token_to_read_private_old_tasks(self):
        # Directly validate the existing P7 visibility gate: it does not
        # become permissive just because ChatGPT used OAuth rather than Bearer.
        with self.assertRaisesRegex(ValueError,"task not found"):
            mcp_gateway.check_visible({"task":{
                "task_id":"00000000-1111-2222-3333-444444444444",
                "target":"claude.code.local",
                "requester":"chatgpt.cxre",
                "project_id":"CX-PAN","status":"COMPLETED"
            }})


if __name__=="__main__":
    unittest.main()
