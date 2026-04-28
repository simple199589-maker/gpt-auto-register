from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class AccountStoreDashboardStatsTests(unittest.TestCase):
    """账号统计中心聚合测试。AI by zb"""

    def setUp(self) -> None:
        """为每个测试创建独立账号数据库。AI by zb"""
        import app.account_store as account_store

        self.account_store = account_store
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.original_db_file = account_store.cfg.files.accounts_db_file
        self.original_accounts_file = account_store.cfg.files.accounts_file
        self.original_initialized = account_store._INITIALIZED
        account_store.cfg.files.accounts_db_file = str(Path(self.temp_dir.name) / "accounts.db")
        account_store.cfg.files.accounts_file = str(Path(self.temp_dir.name) / "registered_accounts.txt")
        account_store._INITIALIZED = False

    def tearDown(self) -> None:
        """恢复账号仓储全局配置。AI by zb"""
        self.account_store.cfg.files.accounts_db_file = self.original_db_file
        self.account_store.cfg.files.accounts_file = self.original_accounts_file
        self.account_store._INITIALIZED = self.original_initialized
        self.temp_dir.cleanup()

    def test_empty_store_returns_zero_dashboard_stats(self) -> None:
        """空账号库应返回完整零值统计结构。AI by zb"""
        stats = self.account_store.build_account_dashboard_stats()

        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["category"], {"normal": 0, "mother": 0})
        self.assertEqual(stats["login"]["success"], 0)
        self.assertEqual(stats["sub2api"]["pending"], 0)
        self.assertEqual(stats["team_manage"]["failed"], 0)
        self.assertEqual(stats["pending_accounts"], 0)
        self.assertEqual(stats["failed_accounts"], 0)
        self.assertEqual(stats["login_success_rate"], 0)
        self.assertEqual(stats["recent_errors"], [])

    def test_mixed_records_return_core_dashboard_stats(self) -> None:
        """混合账号状态应聚合核心流程统计。AI by zb"""
        upsert = self.account_store.upsert_account_record
        upsert(
            "ok@example.com",
            {
                "accountCategory": "normal",
                "loginState": "success",
                "sub2apiState": "success",
                "teamManageState": "success",
                "updatedAt": "20260428_120000",
            },
        )
        upsert(
            "pending@example.com",
            {
                "accountCategory": "mother",
                "loginState": "pending",
                "sub2apiState": "pending",
                "teamManageState": "pending",
                "updatedAt": "20260428_130000",
            },
        )
        upsert(
            "login-failed@example.com",
            {
                "accountCategory": "normal",
                "loginState": "failed",
                "loginMessage": "OTP 超时",
                "sub2apiState": "pending",
                "teamManageState": "disabled",
                "lastError": "登录失败",
                "updatedAt": "20260428_140000",
            },
        )
        upsert(
            "team-failed@example.com",
            {
                "accountCategory": "mother",
                "loginState": "success",
                "sub2apiState": "success",
                "teamManageState": "failed",
                "teamManageMessage": "Team 接口失败",
                "updatedAt": "20260428_150000",
            },
        )

        stats = self.account_store.build_account_dashboard_stats()

        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["category"], {"normal": 2, "mother": 2})
        self.assertEqual(stats["login"], {"pending": 1, "success": 2, "failed": 1, "disabled": 0})
        self.assertEqual(stats["sub2api"], {"pending": 2, "success": 2, "failed": 0, "disabled": 0})
        self.assertEqual(stats["team_manage"], {"pending": 1, "success": 0, "failed": 1, "disabled": 0})
        self.assertEqual(stats["pending_accounts"], 2)
        self.assertEqual(stats["failed_accounts"], 2)
        self.assertEqual(stats["login_success_rate"], 50)
        self.assertEqual(
            [item["email"] for item in stats["recent_errors"]],
            ["team-failed@example.com", "login-failed@example.com"],
        )
        self.assertEqual(stats["recent_errors"][0]["message"], "Team 接口失败")


if __name__ == "__main__":
    unittest.main()
