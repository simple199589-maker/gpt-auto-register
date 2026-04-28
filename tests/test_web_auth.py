from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class WebAuthTests(unittest.TestCase):
    """Web 管理密码鉴权测试。AI by zb"""

    def setUp(self) -> None:
        """创建启用管理密码的 Flask 测试客户端。AI by zb"""
        import app.web_server as web_server

        self.web_server = web_server
        self.client = web_server.app.test_client()
        self.original_password = web_server.cfg.web.admin_password
        web_server.cfg.web.admin_password = "secret-pass"

    def tearDown(self) -> None:
        """恢复测试前的管理密码配置。AI by zb"""
        self.web_server.cfg.web.admin_password = self.original_password

    def test_api_requires_authentication(self) -> None:
        """未登录访问 API 应返回 401。AI by zb"""
        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["authenticated"])

    def test_page_redirects_to_login_when_unauthenticated(self) -> None:
        """未登录访问首页应跳转到登录页。AI by zb"""
        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_rejects_wrong_password(self) -> None:
        """错误管理密码不能登录。AI by zb"""
        response = self.client.post("/api/auth/login", json={"password": "wrong"})

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["success"])

    def test_login_allows_api_access_with_correct_password(self) -> None:
        """正确管理密码登录后应允许访问 API。AI by zb"""
        login_response = self.client.post("/api/auth/login", json={"password": "secret-pass"})
        status_response = self.client.get("/api/auth/status")
        api_response = self.client.get("/api/status")

        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.get_json()["success"])
        self.assertTrue(status_response.get_json()["authenticated"])
        self.assertEqual(api_response.status_code, 200)

    def test_logout_clears_authentication(self) -> None:
        """退出登录后应重新拦截 API 访问。AI by zb"""
        self.client.post("/api/auth/login", json={"password": "secret-pass"})
        logout_response = self.client.post("/api/auth/logout")
        api_response = self.client.get("/api/status")

        self.assertEqual(logout_response.status_code, 200)
        self.assertFalse(logout_response.get_json()["authenticated"])
        self.assertEqual(api_response.status_code, 401)

    def test_config_loader_reads_web_admin_password(self) -> None:
        """配置加载器应读取 web.admin_password。AI by zb"""
        from app.config import ConfigLoader

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("web:\n  admin_password: test-admin\n", encoding="utf-8")

            config = ConfigLoader(config_path=str(config_path)).config

        self.assertEqual(config.web.admin_password, "test-admin")


if __name__ == "__main__":
    unittest.main()
