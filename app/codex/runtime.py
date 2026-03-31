#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex 登录运行时门面。
AI by zb
"""

from .auth import (
    AUTH_JSON_HEADERS,
    COMMON_HEADERS,
    NAVIGATE_HEADERS,
    OPENAI_AUTH_BASE,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    USER_AGENT,
    SentinelTokenGenerator,
    build_auth_json_headers,
    build_sentinel_token,
    create_session,
    decode_auth_session_cookie,
    ensure_workspace_context,
    extract_workspace_id,
    generate_datadog_trace,
    generate_pkce,
    generate_random_birthday,
    generate_random_name,
    perform_http_oauth_login,
    summarize_auth_session_cookies,
)
from .otp import create_mailbox_marker, prompt_for_email_otp, resolve_mailbox_context
from .tokens import (
    CodexRunResult,
    build_sub2api_config,
    build_token_dict,
    decode_jwt_payload,
    get_logger,
    load_runtime_config,
    resolve_proxy,
    run_codex_login,
    save_token_payload,
    upload_to_sub2api,
)

__all__ = [
    "AUTH_JSON_HEADERS",
    "COMMON_HEADERS",
    "CodexRunResult",
    "NAVIGATE_HEADERS",
    "OAUTH_CLIENT_ID",
    "OAUTH_REDIRECT_URI",
    "OPENAI_AUTH_BASE",
    "USER_AGENT",
    "SentinelTokenGenerator",
    "build_auth_json_headers",
    "build_sentinel_token",
    "build_sub2api_config",
    "build_token_dict",
    "create_mailbox_marker",
    "create_session",
    "decode_auth_session_cookie",
    "decode_jwt_payload",
    "ensure_workspace_context",
    "extract_workspace_id",
    "generate_datadog_trace",
    "generate_pkce",
    "generate_random_birthday",
    "generate_random_name",
    "get_logger",
    "load_runtime_config",
    "perform_http_oauth_login",
    "prompt_for_email_otp",
    "resolve_mailbox_context",
    "resolve_proxy",
    "run_codex_login",
    "save_token_payload",
    "summarize_auth_session_cookies",
    "upload_to_sub2api",
]
