from __future__ import annotations

import unittest
from unittest.mock import patch


class LoginSub2ApiTests(unittest.TestCase):
    """登录到 Sub2Api 编排层测试。AI by zb"""

    def test_import_account_defaults_to_pending_login_and_upload(self) -> None:
        """导入账号时应写入待登录与待上传状态。AI by zb"""
        from app import login_sub2api

        captured = {}

        def fake_upsert(email: str, updates: dict) -> dict:
            captured["email"] = email
            captured["updates"] = updates
            return {"email": email, **updates}

        with patch.object(login_sub2api, "get_account_record", return_value=None), patch.object(
            login_sub2api,
            "upsert_account_record",
            side_effect=fake_upsert,
        ):
            account = login_sub2api.import_login_account(
                "User@Example.COM",
                "secret-pass",
                mailbox_context="outlook::User@Example.COM",
            )

        self.assertEqual(captured["email"], "user@example.com")
        self.assertEqual(account["loginState"], "pending")
        self.assertEqual(account["sub2apiState"], "pending")
        self.assertEqual(account["mailboxContext"], "outlook::User@Example.COM")
        self.assertEqual(account["status"], "待登录验证")
        self.assertEqual(account["accountCategory"], "normal")

    def test_import_account_accepts_mother_category(self) -> None:
        """导入账号时应支持写入母号分类。AI by zb"""
        from app import login_sub2api

        captured = {}

        def fake_upsert(email: str, updates: dict) -> dict:
            captured["email"] = email
            captured["updates"] = updates
            return {"email": email, **updates}

        with patch.object(login_sub2api, "get_account_record", return_value=None), patch.object(
            login_sub2api,
            "upsert_account_record",
            side_effect=fake_upsert,
        ):
            account = login_sub2api.import_login_account(
                "mother@example.com",
                "secret-pass",
                account_category="mother",
            )

        self.assertEqual(captured["updates"]["accountCategory"], "mother")
        self.assertEqual(account["accountCategory"], "mother")

    def test_import_outlook_account_defaults_to_outlook_context(self) -> None:
        """导入 Outlook 邮箱时应自动使用 Outlook 上下文。AI by zb"""
        from app import login_sub2api

        captured = {}

        def fake_upsert(email: str, updates: dict) -> dict:
            captured["email"] = email
            captured["updates"] = updates
            return {"email": email, **updates}

        with patch.object(login_sub2api, "get_account_record", return_value=None), patch.object(
            login_sub2api,
            "upsert_account_record",
            side_effect=fake_upsert,
        ):
            account = login_sub2api.import_login_account(
                "tracywhite8678gaj@outlook.com",
                "secret-pass",
            )

        self.assertEqual(captured["email"], "tracywhite8678gaj@outlook.com")
        self.assertEqual(account["mailboxContext"], "outlook::tracywhite8678gaj@outlook.com")

    def test_upload_existing_tokens_does_not_relogin(self) -> None:
        """仅上传已有 token 时不应重新执行 OAuth 登录。AI by zb"""
        from app import login_sub2api

        account = {
            "email": "user@example.com",
            "password": "secret-pass",
            "oauthTokens": {
                "access_token": "access",
                "refresh_token": "refresh",
                "id_token": "id",
            },
        }

        with patch.object(login_sub2api, "get_account_record", return_value=account), patch.object(
            login_sub2api,
            "load_runtime_config",
            return_value={"sub2api": {"base_url": "https://sub.example"}},
        ), patch.object(login_sub2api, "upload_to_sub2api", return_value=True) as upload_mock, patch.object(
            login_sub2api,
            "perform_http_oauth_login",
            side_effect=AssertionError("should not relogin"),
        ), patch.object(login_sub2api, "upsert_account_record", return_value=account):
            result = login_sub2api.upload_existing_tokens_to_sub2api("user@example.com")

        self.assertTrue(result.success)
        self.assertTrue(result.uploaded)
        self.assertEqual(result.stage, "upload")
        upload_mock.assert_called_once()

    def test_login_and_upload_records_login_failure_stage(self) -> None:
        """OAuth 登录失败时应写回登录失败状态。AI by zb"""
        from app import login_sub2api

        updates = {}
        account = {
            "email": "user@example.com",
            "password": "secret-pass",
            "mailboxContext": "mailbox::user@example.com",
        }

        def fake_upsert(email: str, payload: dict) -> dict:
            updates.update(payload)
            return {"email": email, **account, **payload}

        with patch.object(login_sub2api, "get_account_record", return_value=account), patch.object(
            login_sub2api,
            "load_runtime_config",
            return_value={},
        ), patch.object(login_sub2api, "resolve_proxy", return_value=""), patch.object(
            login_sub2api,
            "perform_http_oauth_login",
            return_value=None,
        ), patch.object(login_sub2api, "upsert_account_record", side_effect=fake_upsert):
            result = login_sub2api.login_and_upload_account("user@example.com")

        self.assertFalse(result.success)
        self.assertFalse(result.login_success)
        self.assertEqual(result.stage, "login")
        self.assertEqual(updates["loginState"], "failed")
        self.assertEqual(updates["sub2apiState"], "pending")

    def test_pending_batch_skips_mother_accounts(self) -> None:
        """批量待处理账号应跳过母号。AI by zb"""
        from app import login_sub2api

        records = [
            {
                "email": "normal@example.com",
                "loginState": "pending",
                "sub2apiState": "pending",
                "accountCategory": "normal",
            },
            {
                "email": "mother@example.com",
                "loginState": "pending",
                "sub2apiState": "pending",
                "accountCategory": "mother",
            },
        ]

        with patch.object(login_sub2api, "load_account_records", return_value=records):
            pending = login_sub2api.list_pending_accounts()

        self.assertEqual([item["email"] for item in pending], ["normal@example.com"])


if __name__ == "__main__":
    unittest.main()
