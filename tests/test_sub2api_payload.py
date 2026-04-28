from __future__ import annotations

import unittest

import requests

from app.codex.sub2api import Sub2ApiConfig, Sub2ApiUploader


class Sub2ApiPayloadTests(unittest.TestCase):
    """Sub2Api 上传 payload 测试。AI by zb"""

    def test_default_payload_omits_model_mapping(self) -> None:
        """默认上传时不应发送模型字段。AI by zb"""
        uploader = Sub2ApiUploader(
            requests.Session(),
            Sub2ApiConfig(base_url="https://sub2api.example", client_id="client-id"),
        )

        payload = uploader.build_account_payload(
            "user@example.com",
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "id_token": "id-token",
                "account_id": "account-id",
            },
        )

        self.assertNotIn("model_mapping", payload["credentials"])


if __name__ == "__main__":
    unittest.main()
