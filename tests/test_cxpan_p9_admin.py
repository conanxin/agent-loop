#!/usr/bin/env python3
"""P9 security regression for owner client lifecycle, audit and abuse quotas.

All real OAuth credentials/tokens remain in a temporary SQLite file. Never
runs the production owner's grant-management commands.
"""
import base64
import hashlib
import json
import secrets
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from starlette.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"bridge"))
import oauth_store as store
import oauth_admin as admin
import oauth_server as server

CALLBACK="https://chatgpt.com/connector/oauth/p9-safe-owner-test-client"
RESOURCE=store.RESOURCE


class OwnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="cxpan-p9-owner-")
        self.addCleanup(tmp.cleanup)
        self.old=store.OAUTH_DB
        store.OAUTH_DB=Path(tmp.name)/"oauth.sqlite3"
        self.addCleanup(lambda:setattr(store,"OAUTH_DB",self.old))
        store.set_registration_window(600)
        self.http=TestClient(server.create_app(),
                             base_url="https://www.conanxin.com")
        self.http.__enter__()
        self.addCleanup(lambda:self.http.__exit__(None,None,None))

    def register(self,i=1):
        res=self.http.post("/register",json={
            "redirect_uris":[CALLBACK],
            "token_endpoint_auth_method":"none",
            "grant_types":["authorization_code","refresh_token"],
            "response_types":["code"],
            "scope":"tasks:safe",
            "client_name":"Safe P9 test "+str(i),
        })
        return res

    def start_authorize(self,client_id, state):
        verifier=secrets.token_urlsafe(42)
        challenge=base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        response=self.http.get("/authorize",params={
            "response_type":"code",
            "client_id":client_id,"redirect_uri":CALLBACK,
            "code_challenge":challenge,
            "code_challenge_method":"S256",
            "resource":RESOURCE,"scope":"tasks:safe","state":state
        },follow_redirects=False)
        return response

    def test_client_inventory_hides_secret_fields_and_records_registration(self):
        reg=self.register()
        self.assertEqual(reg.status_code,201,reg.text[:250])
        c=reg.json()
        inventory=admin.registered_clients()
        self.assertEqual(len(inventory),1)
        item=inventory[0]
        self.assertEqual(item["client_id"],c["client_id"])
        self.assertIn("Safe P9 test",item["client_name"])
        self.assertNotIn("client_secret",json.dumps(item))
        self.assertNotIn("client_secret",str(admin.recent_audit()))
        self.assertTrue(any(e["event"]=="client.registered" for e in admin.recent_audit()))

    def test_approval_details_can_be_audited_without_revealing_request_token(self):
        c=self.register().json()
        result=self.start_authorize(c["client_id"],"manual-review")
        self.assertEqual(result.status_code,302)
        self.assertEqual(urlparse(result.headers["location"]).path,"/owner-approve")
        request_id=parse_qs(urlparse(result.headers["location"]).query)["request"][0]
        info=admin.request_info(request_id)
        self.assertEqual(info["scopes"],["tasks:safe"])
        self.assertEqual(info["resource"],RESOURCE)
        self.assertEqual(info["redirect_uri"],CALLBACK)
        self.assertEqual(info["client_name"],"Safe P9 test 1")
        self.assertGreater(info["seconds_left"],0)
        self.assertNotIn(request_id,json.dumps(info))
        self.assertEqual(info["request_sha256_prefix"],
                         store.digest(request_id)[:18])
        server.owner_approve(request_id,"denied")
        self.assertEqual(admin.request_info(request_id)["decision"],"denied")
        self.assertTrue(any(e["event"]=="owner.denied" for e in admin.recent_audit()))

    def test_revoke_client_invalidates_access_refresh_codes_and_pending(self):
        c=self.register().json()
        client_id=c["client_id"]
        access=secrets.token_urlsafe(40)
        refresh=secrets.token_urlsafe(40)
        with store.db_connect(create=True) as db:
            ts=int(time.time())+3600
            for kind,val in (("access",access),("refresh",refresh)):
                db.execute(
                    "INSERT INTO tokens(token_digest,client_id,kind,scopes_json,"
                    "resource,expires_at,family) VALUES(?,?,?,?,?,?,?)",
                    (store.digest(val),client_id,kind,'["tasks:safe"]',
                     RESOURCE,ts,"p9-family"))
            db.execute(
                "INSERT INTO codes(code_digest,client_id,scopes_json,redirect_uri,"
                "redirect_explicit,code_challenge,resource,expires_at)"
                "VALUES(?,?,?,?,?,?,?,?)",
                (store.digest("p9-synthetic-code"),client_id,'["tasks:safe"]',
                 CALLBACK,1,"a"*43,RESOURCE,ts))
            db.commit()
        pending=self.start_authorize(client_id,"pending-before-revoke")
        self.assertEqual(pending.status_code,302)
        self.assertTrue(store.verify_access(access))
        self.assertTrue(admin.revoke_client(client_id))
        self.assertFalse(store.verify_access(access))
        self.assertIsNone(admin.client_metadata(client_id))
        with store.db_connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tokens WHERE "
                         "client_id=? AND revoked=0",(client_id,)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM codes WHERE "
                         "client_id=? AND redeemed=0",(client_id,)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pending WHERE "
                         "client_id=? AND consumed=0",(client_id,)).fetchone()[0],0)
        self.assertTrue(any(e["event"]=="client.revoked"
                            for e in admin.recent_audit()))
        self.assertFalse(admin.revoke_client(client_id))

    def test_new_dcr_registrations_rate_limited_per_30min(self):
        for i in range(admin.MAX_RECENT_DCR):
            r=self.register(i)
            self.assertEqual(r.status_code,201,(i,r.text[:200]))
        extra=self.register(100)
        self.assertEqual(extra.status_code,400)
        self.assertIn("quota",extra.text.lower())
        self.assertEqual(len(admin.registered_clients()),admin.MAX_RECENT_DCR)

    def test_pending_authorization_requests_per_client_are_limited(self):
        c=self.register().json()
        for i in range(admin.MAX_PENDING_PER_CLIENT):
            r=self.start_authorize(c["client_id"],f"pending-{i}")
            self.assertEqual(r.status_code,302)
            self.assertIn("/owner-approve?",r.headers["location"])
        blocked=self.start_authorize(c["client_id"],"pending-over-cap")
        # SDK may redirect authorization errors to the safe registered callback.
        self.assertEqual(blocked.status_code,302)
        self.assertIn("error=",blocked.headers["location"])
        self.assertNotIn("/owner-approve?",blocked.headers["location"])
        with store.db_connect() as db:
            num=db.execute("SELECT count(*) FROM pending WHERE "
                           "client_id=?",(c["client_id"],)).fetchone()[0]
        self.assertEqual(num,admin.MAX_PENDING_PER_CLIENT)


if __name__=="__main__":
    unittest.main()
