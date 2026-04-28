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

    def test_upload_to_sub2api_uses_configured_proxy(self) -> None:
        """Sub2Api 上传应使用全局代理创建 HTTP 会话。AI by zb"""
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
        create_session_mock.assert_called_once_with(proxy="http://10.0.0.8:10809")
        uploader.push_account.assert_called_once_with(
            "user@example.com",
            {"refresh_token": "refresh-token"},
        )

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
