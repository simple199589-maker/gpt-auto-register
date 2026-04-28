from __future__ import annotations

import unittest
from unittest.mock import Mock, patch


class FakeResponse:
    """Codex OAuth 测试响应对象。AI by zb"""

    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = "", headers: dict | None = None):
        """初始化伪响应。AI by zb"""
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}
        self.url = ""
        self.history = []

    def json(self) -> dict:
        """返回伪 JSON 响应体。AI by zb"""
        return self._payload


class FakeSession:
    """Codex OAuth 测试会话对象。AI by zb"""

    def __init__(self, password_response: FakeResponse | None = None, authorize_response: FakeResponse | None = None):
        """初始化伪会话。AI by zb"""
        import requests

        self.cookies = requests.Session().cookies
        self.posts = []
        self.gets = []
        self.password_response = password_response
        self.authorize_response = authorize_response
        self.send_seen_before_provider = False

    def get(self, url: str, **kwargs):
        """记录 GET 请求并返回对应伪响应。AI by zb"""
        self.gets.append((url, kwargs))
        if "sign-in-with-chatgpt/codex/consent" in url:
            return FakeResponse(
                status_code=302,
                headers={"Location": "http://localhost:1455/auth/callback?code=auth-code&state=state"},
            )
        return FakeResponse(status_code=200, payload={})

    def post(self, url: str, **kwargs):
        """记录 POST 请求并返回对应伪响应。AI by zb"""
        self.posts.append((url, kwargs))
        if url.endswith("/api/accounts/authorize/continue"):
            if self.authorize_response is not None:
                return self.authorize_response
            return FakeResponse(status_code=200, payload={"continue_url": "/log-in/password"})
        if url.endswith("/api/accounts/password/verify"):
            if self.password_response is not None:
                return self.password_response
            return FakeResponse(
                status_code=409,
                payload={
                    "continue_url": "/email-verification",
                    "page": {"type": "email_otp_verification"},
                },
            )
        if url.endswith("/api/accounts/email-otp/validate"):
            return FakeResponse(
                status_code=200,
                payload={
                    "continue_url": "/sign-in-with-chatgpt/codex/consent",
                    "page": {"type": "consent"},
                },
            )
        return FakeResponse(status_code=200, payload={})


class CodexManualOtpFlowTests(unittest.TestCase):
    """Codex 手填验证码流程测试。AI by zb"""

    def _run_manual_otp_login(self, fake_session: FakeSession, otp_provider: Mock) -> dict | None:
        """
        执行一次手填验证码登录测试流程。

        参数:
            fake_session: 伪 OAuth 会话
            otp_provider: 验证码提供器
        返回:
            dict | None: token 结果
            AI by zb
        """
        from app.codex import _runtime_impl

        expected_tokens = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "id-token",
        }

        with patch.object(_runtime_impl, "create_session", return_value=fake_session), patch.object(
            _runtime_impl,
            "build_sentinel_token",
            return_value="sentinel-token",
        ), patch.object(_runtime_impl, "_exchange_code_for_token", return_value=expected_tokens):
            tokens = _runtime_impl.perform_http_oauth_login(
                email="thirdparty@example.com",
                password="secret-pass",
                otp_mode="manual",
                otp_provider=otp_provider,
            )

        return tokens

    def test_manual_otp_handles_password_verify_409_challenge(self) -> None:
        """手填验证码模式遇到 Step C 409 OTP 挑战时应等待用户输入。AI by zb"""
        fake_session = FakeSession()
        otp_provider = Mock(return_value="123456")
        expected_tokens = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "id-token",
        }

        tokens = self._run_manual_otp_login(fake_session, otp_provider)

        self.assertEqual(tokens, expected_tokens)
        otp_provider.assert_called_once()
        self.assertTrue(callable(otp_provider.call_args.kwargs.get("resend_callback")))
        validate_calls = [
            kwargs
            for url, kwargs in fake_session.posts
            if url.endswith("/api/accounts/email-otp/validate")
        ]
        self.assertEqual(validate_calls[0]["json"], {"code": "123456"})
        self.assertTrue(validate_calls[0]["headers"].get("oai-device-id"))

    def test_step_b_passwordless_otp_skips_password_verify(self) -> None:
        """Step B 已进入 passwordless OTP 时不应继续提交密码。AI by zb"""
        fake_session = FakeSession(
            authorize_response=FakeResponse(
                status_code=200,
                payload={
                    "continue_url": "https://auth.openai.com/email-verification",
                    "page": {
                        "type": "email_otp_verification",
                        "payload": {"email_verification_mode": "passwordless_login"},
                    },
                },
            )
        )
        otp_provider = Mock(return_value="123456")

        tokens = self._run_manual_otp_login(fake_session, otp_provider)

        self.assertIsNotNone(tokens)
        password_calls = [
            url
            for url, _kwargs in fake_session.posts
            if url.endswith("/api/accounts/password/verify")
        ]
        self.assertEqual(password_calls, [])
        otp_provider.assert_called_once()
        validate_calls = [
            kwargs
            for url, kwargs in fake_session.posts
            if url.endswith("/api/accounts/email-otp/validate")
        ]
        self.assertEqual(validate_calls[0]["json"], {"code": "123456"})

    def test_manual_otp_opens_input_before_resend(self) -> None:
        """手填模式应先开放用户输入，重发时才触发 OTP 发送。AI by zb"""
        fake_session = FakeSession()

        def provide_otp(*args, **kwargs) -> str:
            fake_session.send_seen_before_provider = any(
                url.endswith("/api/accounts/email-otp/send")
                for url, _kwargs in fake_session.gets
            )
            resend_callback = kwargs.get("resend_callback")
            self.assertTrue(callable(resend_callback))
            ok, message = resend_callback()
            self.assertTrue(ok, message)
            return "123456"

        otp_provider = Mock(side_effect=provide_otp)

        tokens = self._run_manual_otp_login(fake_session, otp_provider)

        self.assertIsNotNone(tokens)
        self.assertFalse(fake_session.send_seen_before_provider)
        send_calls = [
            url
            for url, _kwargs in fake_session.gets
            if url.endswith("/api/accounts/email-otp/send")
        ]
        self.assertEqual(len(send_calls), 1)
        send_headers = [
            kwargs["headers"]
            for url, kwargs in fake_session.gets
            if url.endswith("/api/accounts/email-otp/send")
        ]
        self.assertTrue(send_headers[0].get("oai-device-id"))

    def test_manual_otp_handles_password_verify_409_without_continue_payload(self) -> None:
        """手填模式遇到无下一步字段的 Step C 409 也应等待用户输入。AI by zb"""
        fake_session = FakeSession(password_response=FakeResponse(status_code=409, text="Conflict"))
        otp_provider = Mock(return_value="654321")
        expected_tokens = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "id-token",
        }

        tokens = self._run_manual_otp_login(fake_session, otp_provider)

        self.assertEqual(tokens, expected_tokens)
        otp_provider.assert_called_once()
        self.assertTrue(callable(otp_provider.call_args.kwargs.get("resend_callback")))
        validate_calls = [
            kwargs
            for url, kwargs in fake_session.posts
            if url.endswith("/api/accounts/email-otp/validate")
        ]
        self.assertEqual(validate_calls[0]["json"], {"code": "654321"})
        self.assertTrue(validate_calls[0]["headers"].get("oai-device-id"))


if __name__ == "__main__":
    unittest.main()
