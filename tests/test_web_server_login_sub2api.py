from __future__ import annotations

import json
import threading
import time
import unittest
from unittest.mock import Mock, patch


class WebServerLoginSub2ApiTests(unittest.TestCase):
    """Web 登录上传接口测试。AI by zb"""

    def setUp(self) -> None:
        """创建 Flask 测试客户端。AI by zb"""
        from app.web_server import app, manual_otp_broker, state

        self.app = app
        self.client = app.test_client()
        state.is_running = False
        with manual_otp_broker._condition:
            manual_otp_broker._challenges.clear()
            manual_otp_broker._pending_cancels.clear()

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

    def test_login_otp_status_and_resend_use_active_waiter(self) -> None:
        """手填验证码状态与重发应依赖当前等待中的登录会话。AI by zb"""
        import app.web_server as web_server

        email = "otp-resend@example.com"
        resend_mock = Mock(return_value=(True, "已重发"))
        result = {}

        def wait_for_code() -> None:
            result["code"] = web_server.manual_otp_broker.wait_for_code(
                email,
                5,
                resend_callback=resend_mock,
            )

        thread = threading.Thread(target=wait_for_code, daemon=True)
        thread.start()
        for _ in range(20):
            if web_server.manual_otp_broker.get_status(email).get("active"):
                break
            time.sleep(0.05)

        status_response = self.client.get(f"/api/accounts/login-otp/status?email={email}")
        self.assertEqual(status_response.status_code, 200)
        self.assertTrue(status_response.get_json()["active"])
        self.assertFalse(status_response.get_json()["resend_available"])

        early_resend = self.client.post("/api/accounts/login-otp/resend", json={"email": email})
        self.assertEqual(early_resend.status_code, 400)
        resend_mock.assert_not_called()

        with web_server.manual_otp_broker._condition:
            web_server.manual_otp_broker._challenges[email]["nextResendAt"] = time.time() - 1

        resend_response = self.client.post("/api/accounts/login-otp/resend", json={"email": email})
        self.assertEqual(resend_response.status_code, 200)
        self.assertTrue(resend_response.get_json()["success"])
        resend_mock.assert_called_once()

        submit_response = self.client.post("/api/accounts/login-otp", json={"email": email, "code": "123456"})
        self.assertEqual(submit_response.status_code, 200)
        thread.join(timeout=2)
        self.assertEqual(result["code"], "123456")

    def test_login_otp_cancel_releases_active_waiter(self) -> None:
        """关闭弹窗取消时应释放等待中的手填验证码流程。AI by zb"""
        import app.web_server as web_server

        email = "otp-cancel@example.com"
        result = {}

        def wait_for_code() -> None:
            result["code"] = web_server.manual_otp_broker.wait_for_code(email, 5)

        thread = threading.Thread(target=wait_for_code, daemon=True)
        thread.start()
        for _ in range(20):
            if web_server.manual_otp_broker.get_status(email).get("active"):
                break
            time.sleep(0.05)

        cancel_response = self.client.post("/api/accounts/login-otp/cancel", json={"email": email})
        self.assertEqual(cancel_response.status_code, 200)
        self.assertTrue(cancel_response.get_json()["success"])
        thread.join(timeout=2)
        self.assertEqual(result["code"], "")

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

    def test_import_json_accepts_export_payload_with_oauth_tokens(self) -> None:
        """JSON 导入应接受导出文件并保留 OAuth 三件套。AI by zb"""
        import app.web_server as web_server

        captured = []

        def fake_upsert(email: str, updates: dict) -> dict:
            captured.append((email, updates))
            return {"email": email, **updates}

        payload = {
            "mode": "batch",
            "items": [
                {
                    "email": "one@example.com",
                    "password": "one-pass",
                    "accountCategory": "normal",
                    "oauthTokens": {
                        "access_token": "a1",
                        "refresh_token": "r1",
                        "id_token": "i1",
                        "account_id": "acc1",
                    },
                    "oauthOutputFile": "output_tokens/one.json",
                },
                {
                    "email": "two@example.com",
                    "password": "two-pass",
                    "accountCategory": "mother",
                    "oauthTokens": {
                        "access_token": "a2",
                        "refresh_token": "r2",
                        "id_token": "i2",
                        "account_id": "acc2",
                    },
                },
            ],
        }

        with patch.object(web_server, "upsert_account_record", side_effect=fake_upsert):
            response = self.client.post("/api/accounts/import-json", json=payload)

        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["success"])
        self.assertEqual(result["imported"], 2)
        self.assertEqual(captured[0][0], "one@example.com")
        self.assertEqual(captured[0][1]["oauthTokens"]["access_token"], "a1")
        self.assertEqual(captured[0][1]["oauthTokens"]["refresh_token"], "r1")
        self.assertEqual(captured[0][1]["oauthTokens"]["id_token"], "i1")
        self.assertEqual(captured[1][1]["accountCategory"], "mother")

    def test_import_json_accepts_single_account_object(self) -> None:
        """JSON 导入应支持单个账号对象。AI by zb"""
        import app.web_server as web_server

        with patch.object(
            web_server,
            "upsert_account_record",
            return_value={"email": "solo@example.com", "oauthTokens": {"access_token": "access"}},
        ) as upsert_mock:
            response = self.client.post(
                "/api/accounts/import-json",
                json={
                    "email": "solo@example.com",
                    "password": "solo-pass",
                    "oauthTokens": {
                        "access_token": "access",
                        "refresh_token": "refresh",
                        "id_token": "id",
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["imported"], 1)
        upsert_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
