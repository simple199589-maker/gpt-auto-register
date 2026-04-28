from __future__ import annotations

import unittest
from unittest.mock import Mock, patch


class OutlookEmailServiceTests(unittest.TestCase):
    """Outlook 邮箱 provider 测试。AI by zb"""

    def test_create_temp_email_returns_outlook_context(self) -> None:
        """随机领取邮箱应返回 outlook 上下文。AI by zb"""
        from app import outlook_email_service

        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {"email": "demo@outlook.com"}

        with patch.object(outlook_email_service, "_request_outlook_api", return_value=fake_response):
            email, context = outlook_email_service.create_temp_email()

        self.assertEqual(email, "demo@outlook.com")
        self.assertEqual(context, "outlook::demo@outlook.com")

    def test_fetch_emails_normalizes_messages_items(self) -> None:
        """邮件列表应统一为现有邮箱字段结构。AI by zb"""
        from app import outlook_email_service

        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {
            "items": [
                {
                    "id": 101,
                    "subject": "Your OpenAI code is 123456",
                    "sender_email": "noreply@tm.openai.com",
                    "sent_at": "2026-04-05T08:11:22Z",
                    "preview": "Your OpenAI code is 123456",
                }
            ]
        }

        with patch.object(outlook_email_service, "_request_outlook_api", return_value=fake_response):
            emails = outlook_email_service.fetch_emails("outlook::demo@outlook.com")

        self.assertEqual(emails[0]["sender"], "noreply@tm.openai.com")
        self.assertEqual(emails[0]["received_at"], "2026-04-05T08:11:22Z")
        self.assertEqual(emails[0]["verification_code"], "123456")

    def test_send_single_email_reports_unsupported(self) -> None:
        """开放 Outlook provider 未提供发信接口时应明确失败。AI by zb"""
        from app import outlook_email_service

        result = outlook_email_service.send_single_email(
            to_email="user@example.com",
            subject="subject",
            html="<p>body</p>",
            text="body",
        )

        self.assertFalse(result["success"])
        self.assertIn("未提供发送接口", result["message"])

    def test_email_service_dispatches_to_outlook_provider(self) -> None:
        """邮箱服务门面应能按 provider 分发到 Outlook。AI by zb"""
        import app.email_service as email_service
        from app import outlook_email_service

        try:
            email_service.set_email_provider_override("outlook")
            with patch.object(
                outlook_email_service,
                "create_temp_email",
                return_value=("demo@outlook.com", "outlook::demo@outlook.com"),
            ):
                email, context = email_service.create_temp_email()
        finally:
            email_service.set_email_provider_override("")

        self.assertEqual(email, "demo@outlook.com")
        self.assertEqual(context, "outlook::demo@outlook.com")

    def test_email_service_auto_dispatches_outlook_domain(self) -> None:
        """即使全局 provider 为 worker，Outlook 域名也应自动走 Outlook。AI by zb"""
        import app.email_service as email_service
        from app import outlook_email_service

        try:
            email_service.set_email_provider_override("worker")
            with patch.object(outlook_email_service, "fetch_emails", return_value=[{"id": 1}]) as fetch_mock:
                emails = email_service.fetch_emails("mailbox::demo@outlook.com")
        finally:
            email_service.set_email_provider_override("")

        self.assertEqual(emails, [{"id": 1}])
        fetch_mock.assert_called_once_with("mailbox::demo@outlook.com")


if __name__ == "__main__":
    unittest.main()
