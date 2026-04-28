from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from app.team_manage import TeamManageConfig, TeamManageUploader


class TeamManageTests(unittest.TestCase):
    """Team 管理导入测试。AI by zb"""

    def test_build_single_payload_uses_oauth_tokens(self) -> None:
        """单账号导入 payload 应包含文档要求字段。AI by zb"""
        uploader = TeamManageUploader(
            requests.Session(),
            TeamManageConfig(base_url="https://team.joini.cloud", api_key="key", client_id="client-id"),
        )

        payload = uploader.build_single_payload(
            "mother@example.com",
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "id_token": "id-token",
                "account_id": "account-id",
            },
        )

        self.assertEqual(payload["import_type"], "single")
        self.assertEqual(payload["email"], "mother@example.com")
        self.assertEqual(payload["access_token"], "access-token")
        self.assertEqual(payload["refresh_token"], "refresh-token")
        self.assertEqual(payload["client_id"], "client-id")
        self.assertEqual(payload["account_id"], "account-id")

    def test_import_single_account_logs_response_error_without_tokens(self) -> None:
        """Team 管理上传失败时应打印接口 error 且不泄露 token。AI by zb"""
        response = Mock()
        response.status_code = 400
        response.text = (
            '{"success": false, "team_id": null, "email": "mother@example.com", '
            '"message": null, "error": "共发现 1 个 Team 账号,但均已在系统中"}'
        )
        response.headers = {"content-type": "application/json"}
        response.url = "https://team.joini.cloud/admin/teams/import"
        response.json.return_value = {
            "success": False,
            "team_id": None,
            "email": "mother@example.com",
            "message": None,
            "error": "共发现 1 个 Team 账号,但均已在系统中",
        }
        session = Mock()
        session.post.return_value = response
        logger = Mock()
        uploader = TeamManageUploader(
            session,
            TeamManageConfig(base_url="https://team.joini.cloud", api_key="key", client_id="client-id"),
            logger=logger,
        )

        uploaded = uploader.import_single_account(
            "mother@example.com",
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "account_id": "account-id",
            },
        )

        logged = "\n".join(str(call) for call in logger.info.call_args_list + logger.warning.call_args_list)
        self.assertFalse(uploaded)
        self.assertEqual(uploader.last_error_message, "共发现 1 个 Team 账号,但均已在系统中")
        self.assertIn("共发现 1 个 Team 账号,但均已在系统中", logged)
        self.assertNotIn("access-token", logged)
        self.assertNotIn("refresh-token", logged)
        self.assertNotIn("X-API-Key", logged)

    def test_upload_requires_mother_account(self) -> None:
        """非母号账号不允许上传 Team 管理。AI by zb"""
        from app import login_sub2api

        account = {
            "email": "normal@example.com",
            "accountCategory": "normal",
            "oauthTokens": {
                "access_token": "access",
                "refresh_token": "refresh",
                "id_token": "id",
            },
        }

        with patch.object(login_sub2api, "get_account_record", return_value=account):
            result = login_sub2api.upload_existing_tokens_to_team_manage("normal@example.com")

        self.assertFalse(result.success)
        self.assertEqual(result.stage, "category")
        self.assertIn("母号", result.message)

    def test_upload_requires_api_key(self) -> None:
        """Team 管理 API Key 缺失时应返回配置错误。AI by zb"""
        from app import login_sub2api

        account = {
            "email": "mother@example.com",
            "accountCategory": "mother",
            "oauthTokens": {
                "access_token": "access",
                "refresh_token": "refresh",
                "id_token": "id",
            },
        }

        with patch.object(login_sub2api, "get_account_record", return_value=account), patch.object(
            login_sub2api,
            "load_runtime_config",
            return_value={"team_manage": {"base_url": "https://team.joini.cloud", "api_key": ""}},
        ), patch.object(login_sub2api, "upsert_account_record", return_value=account):
            result = login_sub2api.upload_existing_tokens_to_team_manage("mother@example.com")

        self.assertFalse(result.success)
        self.assertEqual(result.stage, "config")
        self.assertIn("API Key", result.message)

    def test_upload_posts_to_team_manage(self) -> None:
        """母号 token 完整时应调用 Team 管理客户端上传。AI by zb"""
        from app import login_sub2api

        account = {
            "email": "mother@example.com",
            "accountCategory": "mother",
            "oauthTokens": {
                "access_token": "access",
                "refresh_token": "refresh",
                "id_token": "id",
            },
        }

        with patch.object(login_sub2api, "get_account_record", return_value=account), patch.object(
            login_sub2api,
            "load_runtime_config",
            return_value={"team_manage": {"base_url": "https://team.joini.cloud", "api_key": "key"}},
        ), patch.object(
            login_sub2api,
            "upload_to_team_manage_with_message",
            return_value=(True, ""),
        ) as upload_mock, patch.object(
            login_sub2api,
            "upsert_account_record",
            return_value=account,
        ):
            result = login_sub2api.upload_existing_tokens_to_team_manage("mother@example.com")

        self.assertTrue(result.success)
        self.assertEqual(result.stage, "team_manage")
        upload_mock.assert_called_once()

    def test_upload_existing_tokens_returns_team_error_message(self) -> None:
        """Team 管理返回错误时接口响应应透传错误详情。AI by zb"""
        from app import login_sub2api

        account = {
            "email": "mother@example.com",
            "accountCategory": "mother",
            "oauthTokens": {
                "access_token": "access",
                "refresh_token": "refresh",
                "id_token": "id",
            },
        }
        team_error = "共发现 1 个 Team 账号,但均已在系统中"

        with patch.object(login_sub2api, "get_account_record", return_value=account), patch.object(
            login_sub2api,
            "load_runtime_config",
            return_value={"team_manage": {"base_url": "https://team.joini.cloud", "api_key": "key"}},
        ), patch.object(
            login_sub2api,
            "upload_to_team_manage_with_message",
            return_value=(False, team_error),
        ), patch.object(
            login_sub2api,
            "upsert_account_record",
            return_value=account,
        ) as upsert_mock:
            result = login_sub2api.upload_existing_tokens_to_team_manage("mother@example.com")

        self.assertFalse(result.success)
        self.assertEqual(result.message, team_error)
        upsert_payload = upsert_mock.call_args.args[1]
        self.assertEqual(upsert_payload["teamManageMessage"], team_error)
        self.assertEqual(upsert_payload["lastError"], team_error)


if __name__ == "__main__":
    unittest.main()
