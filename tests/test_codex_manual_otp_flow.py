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


class AddPhoneAfterOtpSession(FakeSession):
    """OTP 后进入 add-phone 的伪会话。AI by zb"""

    def get(self, url: str, **kwargs):
        """记录 GET 请求并模拟重触发 authorize 才返回 code。AI by zb"""
        self.gets.append((url, kwargs))
        if "/oauth/authorize" in url and kwargs.get("allow_redirects") is False:
            return FakeResponse(
                status_code=302,
                headers={"Location": "http://localhost:1455/auth/callback?code=retry-code&state=state"},
            )
        return FakeResponse(status_code=200, payload={})

    def post(self, url: str, **kwargs):
        """记录 POST 请求并让 OTP 验证后进入 add-phone。AI by zb"""
        self.posts.append((url, kwargs))
        if url.endswith("/api/accounts/authorize/continue"):
            return FakeResponse(status_code=200, payload={"continue_url": "/log-in/password"})
        if url.endswith("/api/accounts/password/verify"):
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
                    "continue_url": "/add-phone",
                    "page": {"type": "add_phone"},
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

    def _run_auto_otp_login(self, fake_session: FakeSession) -> dict | None:
        """
        执行一次自动验证码登录测试流程。

        参数:
            fake_session: 伪 OAuth 会话
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
        ), patch.object(_runtime_impl, "_wait_auto_otp", return_value="123456") as wait_mock, patch.object(
            _runtime_impl,
            "_exchange_code_for_token",
            return_value=expected_tokens,
        ):
            tokens = _runtime_impl.perform_http_oauth_login(
                email="thirdparty@example.com",
                password="secret-pass",
                otp_mode="auto",
                mailbox_context="mailbox::thirdparty@example.com",
            )

        wait_mock.assert_called_once()
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

    def test_step_b_passwordless_otp_skips_password_verify_in_auto_mode(self) -> None:
        """自动模式遇到 Step B passwordless OTP 时也应跳过提交密码。AI by zb"""
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

        tokens = self._run_auto_otp_login(fake_session)

        self.assertIsNotNone(tokens)
        password_calls = [
            url
            for url, _kwargs in fake_session.posts
            if url.endswith("/api/accounts/password/verify")
        ]
        self.assertEqual(password_calls, [])
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

    def test_blank_password_uses_email_otp_without_password_verify(self) -> None:
        """空密码账号应直接使用邮箱验证码模式而不提交密码。AI by zb"""
        fake_session = FakeSession()
        otp_provider = Mock(return_value="123456")
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
                password="",
                otp_mode="manual",
                otp_provider=otp_provider,
            )

        self.assertEqual(tokens, expected_tokens)
        password_calls = [
            url
            for url, _kwargs in fake_session.posts
            if url.endswith("/api/accounts/password/verify")
        ]
        self.assertEqual(password_calls, [])
        otp_provider.assert_called_once()

    def test_authorize_retry_waits_longer_before_final_attempt(self) -> None:
        """authorize 重试最后一次前应等待更久以等会话稳定。AI by zb"""
        from app.codex import _runtime_impl

        session = Mock()
        session.get.return_value = FakeResponse(status_code=302, headers={"Location": "/add-phone"})
        logger = Mock()

        with patch.object(_runtime_impl, "_follow_and_extract_code", return_value=""), patch.object(
            _runtime_impl.time,
            "sleep",
        ) as sleep_mock:
            code = _runtime_impl._retry_authorize_for_code(
                session=session,
                authorize_url="https://auth.openai.com/oauth/authorize",
                oauth_issuer="https://auth.openai.com",
                email="user@example.com",
                logger=logger,
            )

        self.assertIsNone(code)
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(sleep_mock.call_args_list, [])

    def test_extract_consent_state_nonce_handles_next_data(self) -> None:
        """consent 页若是 Next.js __NEXT_DATA__ 应能解析出 state/nonce。AI by zb"""
        from app.codex import _runtime_impl

        html = (
            '<html><head></head><body>'
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"state":"abc123","nonce":"xyz789",'
            '"client":{"name":"Codex"}}},"buildId":"build-1"}'
            '</script></body></html>'
        )
        state, nonce, keys = _runtime_impl._extract_consent_state_nonce(html)
        self.assertEqual(state, "abc123")
        self.assertEqual(nonce, "xyz789")
        self.assertIn("props", keys)
        self.assertIn("buildId", keys)

    def test_extract_consent_state_nonce_falls_back_to_legacy_regex(self) -> None:
        """没有 __NEXT_DATA__ 时仍应能从老式内联 JSON 抠出 state/nonce。AI by zb"""
        from app.codex import _runtime_impl

        html = 'var consent = { "state": "old-state", "nonce": "old-nonce" };'
        state, nonce, keys = _runtime_impl._extract_consent_state_nonce(html)
        self.assertEqual(state, "old-state")
        self.assertEqual(nonce, "old-nonce")
        self.assertEqual(keys, [])

    def test_follow_and_extract_code_handles_relative_url(self) -> None:
        """传入相对路径时也应能正确拼接 oauth_issuer 并发起请求。AI by zb"""
        from app.codex import _runtime_impl

        session = Mock()
        session.get.return_value = FakeResponse(
            status_code=302,
            headers={"Location": "http://localhost:1455/auth/callback?code=relpath-code&state=s"},
        )

        code = _runtime_impl._follow_and_extract_code(
            session,
            "/oauth/authorize?response_type=code",
            "https://auth.openai.com",
        )

        self.assertEqual(code, "relpath-code")
        called_url = session.get.call_args.args[0]
        self.assertTrue(called_url.startswith("https://auth.openai.com/"))

    def test_add_phone_after_otp_retries_authorize_without_consent_post(self) -> None:
        """OTP 后进入 add-phone 时应重触发 authorize 而不是提交 consent。AI by zb"""
        from app.codex import _runtime_impl

        fake_session = AddPhoneAfterOtpSession()
        otp_provider = Mock(return_value="123456")
        expected_tokens = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "id-token",
        }

        with patch.object(_runtime_impl, "create_session", return_value=fake_session), patch.object(
            _runtime_impl,
            "build_sentinel_token",
            return_value="sentinel-token",
        ), patch.object(_runtime_impl.time, "sleep") as sleep_mock, patch.object(
            _runtime_impl,
            "_exchange_code_for_token",
            return_value=expected_tokens,
        ) as exchange_mock:
            tokens = _runtime_impl.perform_http_oauth_login(
                email="thirdparty@example.com",
                password="secret-pass",
                otp_mode="manual",
                otp_provider=otp_provider,
            )

        self.assertIsNone(tokens)
        exchange_mock.assert_not_called()
        self.assertEqual(sleep_mock.call_args_list, [])
        consent_posts = [url for url, _kwargs in fake_session.posts if "consent" in url]
        self.assertEqual(consent_posts, [])


if __name__ == "__main__":
    unittest.main()
