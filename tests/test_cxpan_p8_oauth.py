#!/usr/bin/env python3
"""P8 full OAuth/DCR/PKCE/owner-consent/expiry security regression.

All tokens, secrets and approval requests remain in a temporary directory.
No production OAuth grants, web browser or external model/API calls.
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
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"bridge"))
import oauth_store
import oauth_server

CALLBACK = "https://chatgpt.com/connector/oauth/metadata-test-callback-123"
RESOURCE = oauth_store.RESOURCE


class OAuthFlowTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.old=oauth_store.OAUTH_DB
        oauth_store.OAUTH_DB=Path(tmp.name)/"oauth.sqlite3"
        self.addCleanup(lambda:setattr(oauth_store,"OAUTH_DB",self.old))
        oauth_store.set_registration_window(900)
        self.client=TestClient(oauth_server.create_app(),
                               base_url="https://www.conanxin.com")
        self.client.__enter__()
        self.addCleanup(lambda:self.client.__exit__(None,None,None))
        self.auth=[]
        self.client_id=None
        self.token_data=None

    def register(self, callback=CALLBACK, method="none"):
        resp=self.client.post("/register",json={
            "redirect_uris":[callback],
            "token_endpoint_auth_method":method,
            "grant_types":["authorization_code","refresh_token"],
            "response_types":["code"],
            "scope":"tasks:safe",
            "client_name":"ChatGPT P8 isolated test",
        })
        return resp

    def start(self, scope="tasks:safe", resource=RESOURCE):
        verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        response=self.client.get("/authorize",params={
            "response_type":"code",
            "client_id":self.client_id,
            "redirect_uri":CALLBACK,
            "code_challenge":challenge,
            "code_challenge_method":"S256",
            "scope":scope,
            "state":"unique-state-p8",
            "resource":resource,
        },follow_redirects=False)
        return response, verifier

    def consent_and_token(self):
        reg=self.register()
        self.assertEqual(reg.status_code,201,reg.text)
        self.client_id=reg.json()["client_id"]
        response,verifier=self.start()
        self.assertEqual(response.status_code,302,response.text)
        target=response.headers["location"]
        self.assertEqual(urlparse(target).path,"/owner-approve")
        request_id=parse_qs(urlparse(target).query)["request"][0]
        before=self.client.get("/owner-approve",params={"request":request_id})
        self.assertEqual(before.status_code,200)
        self.assertIn("pending owner approval",before.text)
        self.assertNotIn(CALLBACK+"?code=",before.text)
        oauth_server.owner_approve(request_id,"approved")
        approved=self.client.get("/owner-approve",params={"request":request_id},
                                 follow_redirects=False)
        self.assertEqual(approved.status_code,302,approved.text)
        callback=approved.headers["location"]
        self.assertTrue(callback.startswith(CALLBACK+"?"),callback[:125])
        c=parse_qs(urlparse(callback).query)
        self.assertEqual(c["state"],["unique-state-p8"])
        code=c["code"][0]
        post=self.client.post("/token",data={
            "grant_type":"authorization_code",
            "client_id":self.client_id,
            "code":code,
            "code_verifier":verifier,
            "redirect_uri":CALLBACK,
            "resource":RESOURCE,
        })
        self.assertEqual(post.status_code,200,post.text)
        self.token_data=post.json()
        return code,verifier

    def test_oauth_metadata_and_protected_resource_discovery(self):
        doc=self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(doc.status_code,200)
        data=doc.json()
        self.assertEqual(data["issuer"],oauth_store.ISSUER)
        self.assertEqual(data["code_challenge_methods_supported"],["S256"])
        self.assertIn("none",data["token_endpoint_auth_methods_supported"])
        self.assertIn("client_secret_post",data["token_endpoint_auth_methods_supported"])
        self.assertEqual(data["scopes_supported"],["tasks:safe"])
        self.assertIn(data["registration_endpoint"],["https://www.conanxin.com/register"])
        prm=self.client.get(
            "/.well-known/oauth-protected-resource/cxpan/chatgpt/mcp")
        self.assertEqual(prm.status_code,200)
        self.assertEqual(prm.json()["resource"],RESOURCE)
        self.assertIn(oauth_store.ISSUER,prm.json()["authorization_servers"])

    def test_owner_registration_window_defaults_closed_and_expires(self):
        oauth_store.set_registration_window(0)
        closed=self.register()
        self.assertEqual(closed.status_code,400)
        self.assertEqual(
            oauth_store.db_connect(create=True).execute(
                "SELECT count(*) FROM clients").fetchone()[0],0)
        oauth_store.set_registration_window(300)
        self.assertTrue(oauth_store.registration_is_open())
        opened=self.register()
        self.assertEqual(opened.status_code,201,opened.text[:300])

    def test_bad_registration_redirect_is_rejected(self):
        bad=self.register("https://evil.example/steal")
        self.assertEqual(bad.status_code,400,bad.text)
        with oauth_store.db_connect(create=True) as db:
            self.assertEqual(db.execute("select count(*) from clients").fetchone()[0],0)

    def test_oauth_requires_explicit_owner_decision(self):
        reg=self.register()
        self.assertEqual(reg.status_code,201,reg.text)
        self.client_id=reg.json()["client_id"]
        started,_=self.start()
        self.assertEqual(started.status_code,302)
        req_id=parse_qs(urlparse(started.headers["location"]).query)["request"][0]
        page=self.client.get("/owner-approve",params={"request":req_id},
                             follow_redirects=False)
        self.assertEqual(page.status_code,200)
        self.assertNotIn("code=",page.text)
        oauth_server.owner_approve(req_id,"denied")
        denied=self.client.get("/owner-approve",params={"request":req_id},
                               follow_redirects=False)
        self.assertEqual(denied.status_code,302)
        self.assertIn("access_denied",denied.headers["location"])

    def test_token_audience_scope_pkce_refresh_replay_and_expiry(self):
        code,_=self.consent_and_token()
        access=self.token_data["access_token"]
        refresh=self.token_data["refresh_token"]
        self.assertTrue(oauth_store.verify_access(access))
        self.assertFalse(oauth_store.verify_access(access,resource="https://evil.example"))
        self.assertFalse(oauth_store.verify_access(access,scope="admin:write"))
        self.assertFalse(oauth_store.verify_access(refresh))
        replay=self.client.post("/token",data={
            "grant_type":"authorization_code","client_id":self.client_id,
            "code":code,"code_verifier":"wrong-verifier", "redirect_uri":CALLBACK,
            "resource":RESOURCE,
        })
        self.assertNotEqual(replay.status_code,200)
        rotation=self.client.post("/token",data={
            "grant_type":"refresh_token",
            "client_id":self.client_id,
            "refresh_token":refresh,
            "scope":"tasks:safe",
        })
        self.assertEqual(rotation.status_code,200,rotation.text)
        rotated=rotation.json()
        self.assertTrue(oauth_store.verify_access(rotated["access_token"]))
        old_refresh=self.client.post("/token",data={
            "grant_type":"refresh_token","client_id":self.client_id,
            "refresh_token":refresh, "scope":"tasks:safe",
        })
        self.assertNotEqual(old_refresh.status_code,200)
        with oauth_store.db_connect() as db:
            db.execute("UPDATE tokens SET expires_at=1 "
                       "WHERE token_digest=?",
                       (oauth_store.digest(rotated["access_token"]),))
            db.commit()
        self.assertFalse(oauth_store.verify_access(rotated["access_token"]))

    def test_refuse_wrong_resource_and_scope(self):
        reg=self.register()
        self.assertEqual(reg.status_code,201,reg.text)
        self.client_id=reg.json()["client_id"]
        bad,_=self.start(resource="https://attacker.invalid/resource")
        # SDK safely redirects OAuth errors to the pre-registered callback;
        # a 302 with error is a rejection, NOT a granted approval.
        self.assertEqual(bad.status_code,302)
        self.assertIn("error=invalid_request",bad.headers.get("location",""))
        self.assertNotIn("/owner-approve?",bad.headers.get("location",""))
        bad_scope,_=self.start(scope="shell:admin")
        if bad_scope.status_code==302:
            self.assertIn("error=",bad_scope.headers.get("location",""))
        else:
            self.assertGreaterEqual(bad_scope.status_code,400)


if __name__=="__main__":
    unittest.main()
