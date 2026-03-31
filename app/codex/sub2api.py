#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sub2Api 上传服务。
AI by zb
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests


DEFAULT_SUB2API_MODEL_MAPPING: Dict[str, str] = {
    
    "gpt-3.5-turbo": "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125": "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-1106": "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-16k": "gpt-3.5-turbo-16k",
    "gpt-4": "gpt-4",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-4-turbo-preview": "gpt-4-turbo-preview",
    "gpt-4o": "gpt-4o",
    "gpt-4o-2024-08-06": "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20": "gpt-4o-2024-11-20",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18": "gpt-4o-mini-2024-07-18",
    "gpt-4.5-preview": "gpt-4.5-preview",
    "gpt-4.1": "gpt-4.1",
    "gpt-4.1-mini": "gpt-4.1-mini",
    "gpt-4.1-nano": "gpt-4.1-nano",
    "o1": "o1",
    "o1-preview": "o1-preview",
    "o1-mini": "o1-mini",
    "o1-pro": "o1-pro",
    "o3": "o3",
    "o3-mini": "o3-mini",
    "o3-pro": "o3-pro",
    "o4-mini": "o4-mini",
    "gpt-5": "gpt-5",
    "gpt-5-2025-08-07": "gpt-5-2025-08-07",
    "gpt-5-chat": "gpt-5-chat",
    "gpt-5-chat-latest": "gpt-5-chat-latest",
    "gpt-5-codex": "gpt-5-codex",
    "gpt-5.3-codex-spark": "gpt-5.3-codex-spark",
    "gpt-5-pro": "gpt-5-pro",
    "gpt-5-pro-2025-10-06": "gpt-5-pro-2025-10-06",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-5-mini-2025-08-07": "gpt-5-mini-2025-08-07",
    "gpt-5-nano": "gpt-5-nano",
    "gpt-5-nano-2025-08-07": "gpt-5-nano-2025-08-07",
    "gpt-5.1": "gpt-5.1",
    "gpt-5.1-2025-11-13": "gpt-5.1-2025-11-13",
    "gpt-5.1-chat-latest": "gpt-5.1-chat-latest",
    "gpt-5.1-codex": "gpt-5.1-codex",
    "gpt-5.1-codex-max": "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini": "gpt-5.1-codex-mini",
    "gpt-5.2": "gpt-5.2",
    "gpt-5.2-2025-12-11": "gpt-5.2-2025-12-11",
    "gpt-5.2-chat-latest": "gpt-5.2-chat-latest",
    "gpt-5.2-codex": "gpt-5.2-codex",
    "gpt-5.2-pro": "gpt-5.2-pro",
    "gpt-5.2-pro-2025-12-11": "gpt-5.2-pro-2025-12-11",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-2026-03-05": "gpt-5.4-2026-03-05",
    "gpt-5.3-codex": "gpt-5.3-codex",
    "chatgpt-4o-latest": "chatgpt-4o-latest",
    "gpt-4o-audio-preview": "gpt-4o-audio-preview",
    "gpt-4o-realtime-preview": "gpt-4o-realtime-preview",
}


def normalize_group_ids(raw_group_ids: Any, default: Optional[List[int]] = None) -> List[int]:
    """
    将 group_ids 规范化为整数列表。

    参数:
        raw_group_ids: 原始配置值
        default: 默认分组列表
    返回:
        List[int]: 标准化后的分组 ID 列表
        AI by zb
    """
    fallback = list(default or [2])
    if isinstance(raw_group_ids, list):
        values = [int(item) for item in raw_group_ids if str(item).strip().lstrip("-").isdigit()]
        return values or fallback
    if str(raw_group_ids).strip().lstrip("-").isdigit():
        return [int(raw_group_ids)]
    return fallback


@dataclass(frozen=True)
class Sub2ApiConfig:
    """Sub2Api 配置载体。AI by zb"""

    base_url: str
    bearer: str = ""
    email: str = ""
    password: str = ""
    group_ids: List[int] = field(default_factory=lambda: [5])
    client_id: str = ""
    model_mapping: Dict[str, str] = field(
        default_factory=lambda: DEFAULT_SUB2API_MODEL_MAPPING.copy()
    )


class Sub2ApiUploader:
    """Sub2Api 账号上传器。AI by zb"""

    def __init__(
        self,
        session: requests.Session,
        config: Sub2ApiConfig,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        初始化上传器。

        参数:
            session: requests 会话
            config: Sub2Api 配置
            logger: 日志器
        返回:
            None
            AI by zb
        """
        self.session = session
        self.config = config
        self.logger = logger
        self._auth_lock = threading.Lock()
        self._bearer_holder = [str(config.bearer or "").strip()]

    @staticmethod
    def _decode_jwt_payload(token: str) -> Dict[str, Any]:
        """
        解码 JWT payload，不校验签名。

        参数:
            token: JWT 字符串
        返回:
            Dict[str, Any]: payload 数据
            AI by zb
        """
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return {}
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _build_headers(self, bearer: str = "") -> Dict[str, str]:
        """
        构建上传请求头。

        参数:
            bearer: Bearer token
        返回:
            Dict[str, str]: 请求头
            AI by zb
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.config.base_url}/admin/accounts",
        }
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        return headers

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        timeout: int,
    ) -> Tuple[int, str, Optional[Dict[str, Any]]]:
        """
        发送 JSON POST 请求，并在 301/302 时手动保持 POST 方法重试。

        参数:
            url: 请求地址
            payload: JSON 请求体
            headers: 请求头
            timeout: 超时时间
        返回:
            Tuple[int, str, Optional[Dict[str, Any]]]: 状态码、响应体、解析后的 JSON
            AI by zb
        """
        response = self.session.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout,
            verify=False,
            allow_redirects=False,
        )
        if response.status_code in (301, 302, 307, 308):
            location = str(response.headers.get("Location") or "").strip()
            if location:
                redirect_url = urljoin(url, location)
                if self.logger:
                    self.logger.info("[Sub2Api] 跟随重定向并保持 POST: %s -> %s", url, redirect_url)
                response = self.session.post(
                    redirect_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                    verify=False,
                    allow_redirects=False,
                )

        body = response.text
        try:
            response_data = response.json()
        except Exception:
            response_data = None
        return response.status_code, body, response_data

    @staticmethod
    def _matches_account_email(candidate: Any, email: str) -> bool:
        """
        判断响应对象是否为目标账号。

        参数:
            candidate: 待匹配的响应对象
            email: 目标邮箱
        返回:
            bool: 是否匹配成功
            AI by zb
        """
        if not isinstance(candidate, dict):
            return False
        expected_email = str(email or "").strip()
        name = str(candidate.get("name") or "").strip()
        if name == expected_email:
            return True
        extra = candidate.get("extra") or {}
        if isinstance(extra, dict) and str(extra.get("email") or "").strip() == expected_email:
            return True
        return False

    def _extract_created_account(self, response_data: Any, email: str) -> Optional[Dict[str, Any]]:
        """
        从响应体中提取刚创建的账号对象。

        参数:
            response_data: 已解析的响应 JSON
            email: 目标邮箱
        返回:
            Optional[Dict[str, Any]]: 命中的账号对象，未命中则返回 None
            AI by zb
        """
        if not isinstance(response_data, dict):
            return None
        data = response_data.get("data")
        if self._matches_account_email(data, email):
            return data
        if not isinstance(data, dict):
            return None
        for key in ("item", "account", "result"):
            candidate = data.get(key)
            if self._matches_account_email(candidate, email):
                return candidate
        return None

    @staticmethod
    def _summarize_response(response_data: Any, body: str) -> str:
        """
        生成不包含敏感字段的响应摘要。

        参数:
            response_data: 已解析的响应 JSON
            body: 原始响应文本
        返回:
            str: 脱敏摘要
            AI by zb
        """
        if isinstance(response_data, dict):
            summary: Dict[str, Any] = {
                "code": response_data.get("code"),
                "message": response_data.get("message"),
            }
            data = response_data.get("data")
            if isinstance(data, dict):
                summary["data_keys"] = list(data.keys())[:10]
                items = data.get("items")
                if isinstance(items, list):
                    summary["items_count"] = len(items)
            return json.dumps(summary, ensure_ascii=False)
        return str(body or "")[:200]

    def login(self) -> str:
        """
        使用后台账号登录 Sub2Api 并获取 bearer。

        返回:
            str: bearer token
            AI by zb
        """
        if not self.config.base_url or not self.config.email or not self.config.password:
            return ""
        try:
            status_code, body, data = self._post_json(
                f"{self.config.base_url}/api/v1/auth/login",
                payload={"email": self.config.email, "password": self.config.password},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=15,
            )
        except Exception as exc:
            if self.logger:
                self.logger.warning("[Sub2Api] 登录失败: %s", exc)
            return ""

        if not isinstance(data, dict):
            if self.logger:
                self.logger.warning("[Sub2Api] 登录响应异常 | HTTP %s | %s", status_code, str(body)[:200])
            return ""

        token = (
            data.get("token")
            or data.get("access_token")
            or (data.get("data") or {}).get("token")
            or (data.get("data") or {}).get("access_token")
            or ""
        )
        if not token and self.logger:
            self.logger.warning(
                "[Sub2Api] 登录未返回 token | HTTP %s | %s",
                status_code,
                self._summarize_response(data, body),
            )
        return str(token).strip()

    def build_account_payload(self, email: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建 Sub2Api 账号上传负载。

        参数:
            email: 账号邮箱
            tokens: OpenAI OAuth tokens
        返回:
            Dict[str, Any]: 上传 payload
            AI by zb
        """
        access_token = str(tokens.get("access_token") or "")
        refresh_token = str(tokens.get("refresh_token") or "")
        id_token = str(tokens.get("id_token") or "")

        access_payload = self._decode_jwt_payload(access_token) if access_token else {}
        auth_payload = access_payload.get("https://api.openai.com/auth") or {}
        chatgpt_account_id = auth_payload.get("chatgpt_account_id") or tokens.get("account_id") or ""
        chatgpt_user_id = auth_payload.get("chatgpt_user_id") or ""
        exp_timestamp = access_payload.get("exp", 0)
        expires_at = (
            exp_timestamp
            if isinstance(exp_timestamp, int) and exp_timestamp > 0
            else int(time.time()) + 863999
        )

        id_payload = self._decode_jwt_payload(id_token) if id_token else {}
        id_auth_payload = id_payload.get("https://api.openai.com/auth") or {}
        organization_id = id_auth_payload.get("organization_id") or ""
        if not organization_id:
            organizations = id_auth_payload.get("organizations") or []
            if organizations:
                organization_id = str((organizations[0] or {}).get("id") or "")

        return {
            "auto_pause_on_expired": True,
            "concurrency": 10,
            "credentials": {
                "access_token": access_token,
                "chatgpt_account_id": chatgpt_account_id,
                "chatgpt_user_id": chatgpt_user_id,
                "client_id": self.config.client_id,
                "expires_in": 863999,
                "expires_at": expires_at,
                "model_mapping": self.config.model_mapping,
                "organization_id": organization_id,
                "refresh_token": refresh_token,
            },
            "extra": {
                "email": email,
                "openai_oauth_responses_websockets_v2_enabled": True,
                "openai_oauth_responses_websockets_v2_mode": "off",
            },
            "group_ids": list(self.config.group_ids or [5]),
            "name": email,
            "notes": "",
            "platform": "openai",
            "priority": 1,
            "rate_multiplier": 1,
            "type": "oauth",
        }

    def push_account(self, email: str, tokens: Dict[str, Any]) -> bool:
        """
        上传账号到 Sub2Api。

        参数:
            email: 账号邮箱
            tokens: OpenAI OAuth tokens
        返回:
            bool: 是否上传成功
            AI by zb
        """
        if not self.config.base_url or not str(tokens.get("refresh_token") or "").strip():
            return False

        url = f"{self.config.base_url}/api/v1/admin/accounts"
        payload = self.build_account_payload(email, tokens)

        def do_request(headers: Dict[str, str]) -> tuple[int, str, Optional[Dict[str, Any]]]:
            try:
                return self._post_json(
                    url,
                    payload=payload,
                    headers=headers,
                    timeout=20,
                )
            except Exception as exc:
                return 0, str(exc), None

        bearer = self._bearer_holder[0]
        headers = self._build_headers(bearer)
        status_code, body, response_data = do_request(headers)

        if status_code == 401 and self.config.email and self.config.password:
            with self._auth_lock:
                if self._bearer_holder[0] == bearer:
                    new_token = self.login()
                    if new_token:
                        self._bearer_holder[0] = new_token
            headers = self._build_headers(self._bearer_holder[0])
            status_code, body, response_data = do_request(headers)

        created_account = self._extract_created_account(response_data, email)
        ok = status_code in (200, 201) and created_account is not None
        if self.logger:
            if ok:
                self.logger.info(
                    "[Sub2Api] 上传成功: %s | HTTP %s | account_id=%s",
                    email,
                    status_code,
                    created_account.get("id"),
                )
            else:
                self.logger.warning(
                    "[Sub2Api] 上传失败或响应异常: %s | HTTP %s | %s",
                    email,
                    status_code,
                    self._summarize_response(response_data, body),
                )
        return ok
