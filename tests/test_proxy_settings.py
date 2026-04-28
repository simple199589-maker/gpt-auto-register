from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class ProxySettingsTests(unittest.TestCase):
    """代理设置测试。AI by zb"""

    def test_resolve_proxy_from_enabled_host_and_port(self) -> None:
        """启用代理时应根据 IP 与端口生成 requests 代理地址。AI by zb"""
        from app.codex._runtime_impl import resolve_proxy

        proxy = resolve_proxy(
            {
                "proxy": {
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": 7890,
                }
            }
        )

        self.assertEqual(proxy, "http://127.0.0.1:7890")

    def test_upload_to_sub2api_uses_direct_session_when_proxy_configured(self) -> None:
        """Sub2Api 上传即使配置代理也应直连内部接口。AI by zb"""
        from app.codex import _runtime_impl

        session = Mock()
        uploader = Mock()
        uploader.push_account.return_value = True
        config = {
            "proxy": {"enabled": True, "host": "10.0.0.8", "port": 10809},
            "sub2api": {"base_url": "https://sub2api.example"},
        }

        with patch.object(_runtime_impl, "create_session", return_value=session) as create_session_mock, patch.object(
            _runtime_impl,
            "Sub2ApiUploader",
            return_value=uploader,
        ):
            result = _runtime_impl.upload_to_sub2api(
                "user@example.com",
                {"refresh_token": "refresh-token"},
                config,
            )

        self.assertTrue(result)
        create_session_mock.assert_called_once_with()
        uploader.push_account.assert_called_once_with(
            "user@example.com",
            {"refresh_token": "refresh-token"},
        )

    def test_codex_oauth_login_still_uses_configured_proxy(self) -> None:
        """Codex OAuth 登录链路仍应使用配置代理。AI by zb"""
        from app.codex import _runtime_impl

        tokens = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "id-token",
        }

        with patch.object(
            _runtime_impl,
            "load_runtime_config",
            return_value={"proxy": {"enabled": True, "host": "10.0.0.8", "port": 10809}},
        ), patch.object(
            _runtime_impl,
            "perform_http_oauth_login",
            return_value=tokens,
        ) as oauth_mock, patch.object(
            _runtime_impl,
            "save_token_payload",
            return_value="",
        ):
            result = _runtime_impl.run_codex_login("user@example.com", "secret-pass", upload=False)

        self.assertTrue(result.success)
        self.assertEqual(oauth_mock.call_args.kwargs["proxy"], "http://10.0.0.8:10809")

    def test_worker_email_api_does_not_pass_proxy_argument(self) -> None:
        """Worker 邮箱接口请求不应显式携带代理参数。AI by zb"""
        from app import email_service

        with patch.object(email_service, "EMAIL_WORKER_URL", "https://mail.example"), patch.object(
            email_service,
            "EMAIL_ADMIN_PASSWORD",
            "secret",
        ), patch.object(email_service.http_session, "request", return_value=Mock()) as request_mock:
            email_service._request_email_api("GET", "/api/generate", params={"mode": "human"})

        self.assertNotIn("proxies", request_mock.call_args.kwargs)

    def test_shared_http_session_factory_does_not_apply_global_proxy(self) -> None:
        """内部服务共享 HTTP 会话不应默认套用全局代理。AI by zb"""
        from app import utils

        session = utils.create_http_session()

        self.assertEqual(session.proxies, {})

    def test_outlook_email_api_does_not_pass_proxy_argument(self) -> None:
        """Outlook 邮箱接口请求不应显式携带代理参数。AI by zb"""
        from app import outlook_email_service

        with patch.object(outlook_email_service, "OUTLOOK_BASE_URL", "https://outlook.example"), patch.object(
            outlook_email_service,
            "OUTLOOK_API_KEY",
            "secret",
        ), patch.object(outlook_email_service.http_session, "request", return_value=Mock()) as request_mock:
            outlook_email_service._request_outlook_api("GET", "/api/open/mailboxes/demo/messages")

        self.assertNotIn("proxies", request_mock.call_args.kwargs)

    def test_team_manage_upload_uses_direct_session_when_proxy_configured(self) -> None:
        """Team 管理上传即使配置代理也应直连内部接口。AI by zb"""
        from app import login_sub2api

        session = Mock()
        uploader = Mock()
        uploader.import_single_account.return_value = True
        config = {
            "proxy": {"enabled": True, "host": "10.0.0.8", "port": 10809},
            "team_manage": {"base_url": "https://team.joini.cloud", "api_key": "secret"},
        }

        with patch.object(login_sub2api, "create_session", return_value=session) as create_session_mock, patch.object(
            login_sub2api,
            "TeamManageUploader",
            return_value=uploader,
        ):
            result = login_sub2api.upload_to_team_manage(
                "mother@example.com",
                {"access_token": "access-token", "refresh_token": "refresh-token", "id_token": "id-token"},
                config,
            )

        self.assertTrue(result)
        create_session_mock.assert_called_once_with()
        uploader.import_single_account.assert_called_once()

    def test_config_loader_persists_proxy_settings(self) -> None:
        """设置页保存代理配置时应写入 config.yaml 并刷新 cfg。AI by zb"""
        from app.config import ConfigLoader

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "sub2api:\n  auto_upload_sub2api: true\n  group_ids: [2]\n",
                encoding="utf-8",
            )
            loader = ConfigLoader(config_path=str(config_path))

            config = loader.update_automation_settings(
                proxy_enabled=True,
                proxy_host="127.0.0.1",
                proxy_port=7890,
            )

            self.assertTrue(config.proxy.enabled)
            self.assertEqual(config.proxy.host, "127.0.0.1")
            self.assertEqual(config.proxy.port, 7890)
            saved_text = config_path.read_text(encoding="utf-8")
            self.assertIn("proxy:", saved_text)
            self.assertIn("enabled: true", saved_text)
            self.assertIn('host: "127.0.0.1"', saved_text)
            self.assertIn("port: 7890", saved_text)


if __name__ == "__main__":
    unittest.main()
