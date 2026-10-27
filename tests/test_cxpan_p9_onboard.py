#!/usr/bin/env python3
"""Trusted interactive onboarding safety tests; no actual SSH, credentials, UI."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("cxpan_connect_chatgpt_test",
                                             ROOT/"bridge/connect_chatgpt.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VALID_ID="A" * 45
VALID={
 "client_id":"00000000-1111-2222-3333-444444444444",
 "client_name":"CX-PAN safe test",
 "redirect_uri":"https://chatgpt.com/connector/oauth/callback-test-123456",
 "scopes":["tasks:safe"],
 "resource":"https://www.conanxin.com/cxpan/chatgpt/mcp",
 "seconds_left":300,
 "decision":"pending",
 "consumed":False,
 "request_sha256_prefix":"00aa11bb22cc33dd44",
}


class OwnerInteractiveOnboardTests(unittest.TestCase):
    def setUp(self):
        self.argv_patch=patch.object(mod.sys,"argv",["cxpan-p9-onboard"])
        self.argv_patch.start()
        self.addCleanup(self.argv_patch.stop)

    def test_valid_client_and_only_safe_scope(self):
        v=mod.verify_owner_view(VALID)
        self.assertEqual(v["scopes"],["tasks:safe"])
        self.assertEqual(v["resource"],mod.PUBLIC_OAUTH_RESOURCE)
        self.assertEqual(v["client_name"],"CX-PAN safe test")
        self.assertNotIn("request_id",v)

    def test_reject_injected_oauth_request_id(self):
        for x in ("", "../etc/passwd", "ABC", "A"*200,
                  "A"*40+";rm -rf /", "A"*41+"$(id)", "A"*41+"\n"):
            with self.subTest(x=x[:12]),self.assertRaises(ValueError):
                mod.validate_request_id(x)
        self.assertEqual(mod.validate_request_id(VALID_ID),VALID_ID)

    def test_reject_wrong_scope_audience_redirect_and_expiry(self):
        for changes in (
            {"scopes":["shell:write"]},
            {"resource":"https://evil.example/"},
            {"redirect_uri":"https://attacker.example/collect"},
            {"seconds_left":0},
            {"decision":"approved"},
            {"consumed":True},
        ):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                mod.verify_owner_view({**VALID,**changes})

    def test_no_tty_does_not_even_open_dcr_window(self):
        with patch.object(mod.sys.stdin,"isatty",return_value=False),patch.object(
            mod,"ssh_owner"
        ) as remote:
            code=mod.main()
        self.assertEqual(code,2)
        remote.assert_not_called()

    def test_owner_must_type_START_before_any_registration(self):
        with patch.object(mod.sys.stdin,"isatty",return_value=True),patch.object(
            mod.sys.stdout,"isatty",return_value=True
        ),patch("builtins.input",return_value="YES"),patch.object(
            mod,"ssh_owner"
        ) as remote:
            code=mod.main()
        self.assertEqual(code,1)
        remote.assert_not_called()

    def test_approval_requires_exact_explicit_APPROVE_and_closes_window(self):
        calls=[]
        def fake_ssh(*args):
            calls.append(args)
            if args[0]=="request-info":return json.dumps(VALID)
            return "SAFE_STATUS"
        with patch.object(mod.sys.stdin,"isatty",return_value=True),patch.object(
            mod.sys.stdout,"isatty",return_value=True
        ),patch("builtins.input",side_effect=["START","DECLINE"]),patch.object(
            mod,"getpass",return_value=VALID_ID
        ),patch.object(mod,"ssh_owner",side_effect=fake_ssh):
            code=mod.main()
        self.assertEqual(code,1)
        self.assertEqual(calls[0],("registration-open","--minutes","10"))
        self.assertEqual(calls[1],("request-info",VALID_ID))
        self.assertEqual(calls[-1],("registration-close",))
        self.assertFalse(any(x[0]=="approve" for x in calls))

    def test_owner_APPROVE_is_one_explicit_action(self):
        calls=[]
        def fake_ssh(*args):
            calls.append(args)
            if args[0]=="request-info":return json.dumps(VALID)
            return "SAFE_STATUS"
        with patch.object(mod.sys.stdin,"isatty",return_value=True),patch.object(
            mod.sys.stdout,"isatty",return_value=True
        ),patch("builtins.input",side_effect=["START","APPROVE"]),patch.object(
            mod,"getpass",return_value=VALID_ID
        ),patch.object(mod,"ssh_owner",side_effect=fake_ssh):
            code=mod.main()
        self.assertEqual(code,0)
        self.assertEqual([x[0] for x in calls],
                         ["registration-open","request-info","approve",
                          "registration-close"])


if __name__=="__main__":
    unittest.main()
