from __future__ import annotations

import unittest
import sqlite3


class AccountStoreWebPayloadTests(unittest.TestCase):
    """账号仓储前端 payload 测试。AI by zb"""

    def test_sanitize_account_record_includes_login_fields(self) -> None:
        """前端展示数据应包含登录状态与登录消息。AI by zb"""
        from app.account_store import sanitize_account_record_for_web

        payload = sanitize_account_record_for_web(
            {
                "email": "user@example.com",
                "password": "secret-pass",
                "loginState": "failed",
                "loginMessage": "未获取到 OAuth 三件套",
                "loginVerifiedAt": "20260428_120000",
            }
        )

        self.assertEqual(payload["loginStatus"], "failed")
        self.assertEqual(payload["loginState"], "failed")
        self.assertEqual(payload["loginMessage"], "未获取到 OAuth 三件套")
        self.assertEqual(payload["loginVerifiedAt"], "20260428_120000")

    def test_sanitize_account_record_includes_category_and_team_manage(self) -> None:
        """前端展示数据应包含分类与 Team 管理状态。AI by zb"""
        from app.account_store import sanitize_account_record_for_web

        payload = sanitize_account_record_for_web(
            {
                "email": "mother@example.com",
                "password": "secret-pass",
                "accountCategory": "mother",
                "teamManageUploaded": True,
                "teamManageState": "success",
                "teamManageStatus": "已上传",
                "teamManageMessage": "导入成功",
                "teamManageUploadedAt": "20260428_130000",
                "oauthTokens": {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "id_token": "id",
                },
            }
        )

        self.assertEqual(payload["accountCategory"], "mother")
        self.assertEqual(payload["accountCategoryLabel"], "母号")
        self.assertTrue(payload["isMotherAccount"])
        self.assertTrue(payload["teamManageUploaded"])
        self.assertEqual(payload["teamManageState"], "success")
        self.assertTrue(payload["canUploadTeamManage"])

    def test_ensure_schema_adds_category_before_indexes_for_existing_database(self) -> None:
        """旧数据库补列应先于新索引创建执行。AI by zb"""
        from app.account_store import _ensure_schema

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE accounts (
                email TEXT PRIMARY KEY,
                password TEXT NOT NULL DEFAULT 'N/A',
                status_text TEXT NOT NULL DEFAULT '',
                overall_status TEXT NOT NULL DEFAULT 'pending',
                registration_status TEXT NOT NULL DEFAULT 'pending',
                login_status TEXT NOT NULL DEFAULT 'pending',
                login_message TEXT NOT NULL DEFAULT '',
                login_verified_at TEXT NOT NULL DEFAULT '',
                access_token TEXT NOT NULL DEFAULT '',
                mailbox_context TEXT NOT NULL DEFAULT '',
                session_info_json TEXT NOT NULL DEFAULT '{}',
                plus_called INTEGER NOT NULL DEFAULT 0,
                plus_success INTEGER NOT NULL DEFAULT 0,
                plus_status TEXT NOT NULL DEFAULT 'idle',
                plus_status_text TEXT NOT NULL DEFAULT '',
                plus_message TEXT NOT NULL DEFAULT '',
                plus_request_id TEXT NOT NULL DEFAULT '',
                plus_called_at TEXT NOT NULL DEFAULT '',
                sub2api_uploaded INTEGER NOT NULL DEFAULT 0,
                sub2api_status TEXT NOT NULL DEFAULT 'pending',
                sub2api_status_text TEXT NOT NULL DEFAULT '',
                sub2api_message TEXT NOT NULL DEFAULT '',
                sub2api_uploaded_at TEXT NOT NULL DEFAULT '',
                sub2api_auto_upload_enabled INTEGER NOT NULL DEFAULT 0,
                oauth_tokens_json TEXT NOT NULL DEFAULT '{}',
                oauth_output_file TEXT NOT NULL DEFAULT '',
                delivery_info_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                last_error TEXT NOT NULL DEFAULT ''
            );
            """
        )

        _ensure_schema(connection)
        columns = {
            str(row["name"] or "")
            for row in connection.execute("PRAGMA table_info(accounts)").fetchall()
        }

        self.assertIn("account_category", columns)
        self.assertIn("team_manage_status", columns)


if __name__ == "__main__":
    unittest.main()
