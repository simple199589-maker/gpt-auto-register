from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch


class WebServerLoginSub2ApiTests(unittest.TestCase):
    """Web 登录上传接口测试。AI by zb"""

    def setUp(self) -> None:
        """创建 Flask 测试客户端。AI by zb"""
        from app.web_server import app, state

        self.app = app
        self.client = app.test_client()
        state.is_running = False

    def test_import_endpoint_imports_login_account(self) -> None:
        """导入接口应调用登录账号导入编排。AI by zb"""
        import app.web_server as web_server

        with patch.object(
            web_server.login_sub2api,
            "import_login_account",
            return_value={"email": "user@example.com", "loginState": "pending"},
        ) as import_mock:
            response = self.client.post(
                "/api/accounts/import",
                json={"email": "user@example.com", "password": "secret-pass", "account_category": "mother"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        import_mock.assert_called_once_with(
            email="user@example.com",
            password="secret-pass",
            mailbox_context="",
            account_category="mother",
        )

    def test_old_retry_plus_endpoint_is_disabled(self) -> None:
        """旧 Plus 重试接口应返回 410。AI by zb"""
        response = self.client.post("/api/accounts/retry-plus", json={"email": "user@example.com"})

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.get_json()["stage"], "disabled")

    def test_upload_sub2api_uses_existing_token_only(self) -> None:
        """手动上传接口应只复用已保存 token。AI by zb"""
        import app.web_server as web_server

        result = Mock()
        result.to_dict.return_value = {
            "success": True,
            "email": "user@example.com",
            "login_success": True,
            "uploaded": True,
            "stage": "upload",
            "message": "上传成功",
        }
        result.success = True
        result.uploaded = True
        result.message = "上传成功"
        result.stage = "upload"

        with patch.object(
            web_server.login_sub2api,
            "upload_existing_tokens_to_sub2api",
            return_value=result,
        ) as upload_mock, patch.object(web_server, "get_account_record", return_value={"email": "user@example.com"}):
            response = self.client.post("/api/accounts/upload-sub2api", json={"email": "user@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        upload_mock.assert_called_once_with("user@example.com")

    def test_login_endpoint_passes_otp_mode_and_upload_targets(self) -> None:
        """登录上传接口应透传验证码模式与上传目标。AI by zb"""
        import app.web_server as web_server

        result = Mock()
        result.to_dict.return_value = {
            "success": True,
            "email": "mother@example.com",
            "login_success": True,
            "uploaded": True,
            "stage": "upload",
            "message": "登录成功",
        }

        with patch.object(
            web_server.login_sub2api,
            "login_and_upload_account",
            return_value=result,
        ) as login_mock, patch.object(web_server, "get_account_record", return_value={"email": "mother@example.com"}):
            response = self.client.post(
                "/api/accounts/login-sub2api",
                json={
                    "email": "mother@example.com",
                    "otp_mode": "manual",
                    "upload_targets": ["sub2api", "team_manage"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        login_mock.assert_called_once_with(
            email="mother@example.com",
            otp_mode="manual",
            skip_upload=False,
            upload_targets=["sub2api", "team_manage"],
            otp_provider=web_server.manual_otp_provider,
        )

    def test_upload_team_manage_endpoint_uses_existing_token_only(self) -> None:
        """Team 管理上传接口应复用已保存 token。AI by zb"""
        import app.web_server as web_server

        result = Mock()
        result.to_dict.return_value = {
            "success": True,
            "email": "mother@example.com",
            "login_success": True,
            "uploaded": True,
            "stage": "team_manage",
            "message": "Team 管理上传成功",
        }
        result.success = True
        result.uploaded = True
        result.message = "Team 管理上传成功"
        result.stage = "team_manage"

        with patch.object(
            web_server.login_sub2api,
            "upload_existing_tokens_to_team_manage",
            return_value=result,
        ) as upload_mock, patch.object(web_server, "get_account_record", return_value={"email": "mother@example.com"}):
            response = self.client.post("/api/accounts/upload-team-manage", json={"email": "mother@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        upload_mock.assert_called_once_with("mother@example.com")

    def test_export_single_account_includes_oauth_tokens(self) -> None:
        """单账号导出应包含 OAuth 三件套。AI by zb"""
        import app.web_server as web_server

        account = {
            "email": "user@example.com",
            "password": "secret-pass",
            "oauthTokens": {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "id_token": "id-token",
                "account_id": "account-id",
            },
        }

        with patch.object(web_server, "get_account_record", return_value=account):
            response = self.client.get("/api/accounts/export?email=user@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["mode"], "single")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["oauthTokens"]["access_token"], "access-token")
        self.assertEqual(payload["items"][0]["oauthTokens"]["refresh_token"], "refresh-token")
        self.assertEqual(payload["items"][0]["oauthTokens"]["id_token"], "id-token")

    def test_export_batch_accounts_uses_filters_without_page_limit(self) -> None:
        """批量导出应按筛选条件导出全部匹配账号。AI by zb"""
        import app.web_server as web_server

        first_page = {
            "items": [
                {
                    "email": "one@example.com",
                    "password": "one-pass",
                    "oauthTokens": {"access_token": "a1", "refresh_token": "r1", "id_token": "i1"},
                }
            ],
            "pagination": {"page": 1, "page_size": 100, "total": 2, "total_pages": 2},
        }
        second_page = {
            "items": [
                {
                    "email": "two@example.com",
                    "password": "two-pass",
                    "oauthTokens": {"access_token": "a2", "refresh_token": "r2", "id_token": "i2"},
                }
            ],
            "pagination": {"page": 2, "page_size": 100, "total": 2, "total_pages": 2},
        }

        with patch.object(web_server, "query_account_records", side_effect=[first_page, second_page]) as query_mock:
            response = self.client.get(
                "/api/accounts/export?login_status=success&sub2api_status=success&account_category=normal"
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["mode"], "batch")
        self.assertEqual(payload["count"], 2)
        self.assertEqual([item["email"] for item in payload["items"]], ["one@example.com", "two@example.com"])
        self.assertEqual(payload["items"][1]["oauthTokens"]["refresh_token"], "r2")
        self.assertEqual(query_mock.call_count, 2)
        first_call = query_mock.call_args_list[0].kwargs
        self.assertEqual(first_call["login_status"], "success")
        self.assertEqual(first_call["sub2api_status"], "success")
        self.assertEqual(first_call["account_category"], "normal")
        self.assertEqual(first_call["page_size"], 100)


if __name__ == "__main__":
    unittest.main()
