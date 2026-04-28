"""
Team 管理单账号导入客户端。
AI by zb
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests


@dataclass(frozen=True)
class TeamManageConfig:
    """Team 管理导入配置。AI by zb"""

    base_url: str = "https://team.joini.cloud"
    api_key: str = ""
    client_id: str = ""


class TeamManageUploader:
    """Team 管理单账号导入器。AI by zb"""

    def __init__(
        self,
        session: requests.Session,
        config: TeamManageConfig,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        初始化 Team 管理上传器。

        参数:
            session: requests 会话
            config: Team 管理配置
            logger: 日志器
        返回:
            None
            AI by zb
        """
        self.session = session
        self.config = config
        self.logger = logger
        self.last_error_message = ""

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
            parts = str(token or "").split(".")
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

    def _extract_account_id(self, tokens: Dict[str, Any]) -> str:
        """
        从 token 字段中提取 Team account_id。

        参数:
            tokens: OAuth token 字典
        返回:
            str: account_id
            AI by zb
        """
        explicit_account_id = str((tokens or {}).get("account_id") or "").strip()
        if explicit_account_id:
            return explicit_account_id

        access_payload = self._decode_jwt_payload(str((tokens or {}).get("access_token") or ""))
        auth_payload = access_payload.get("https://api.openai.com/auth") or {}
        if not isinstance(auth_payload, dict):
            return ""
        return str(auth_payload.get("chatgpt_account_id") or "").strip()

    def build_single_payload(self, email: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建 Team 管理单账号导入 payload。

        参数:
            email: 账号邮箱
            tokens: OAuth token 字典
        返回:
            Dict[str, Any]: 导入 payload
            AI by zb
        """
        normalized_tokens = tokens or {}
        payload = {
            "import_type": "single",
            "email": str(email or "").strip(),
            "access_token": str(normalized_tokens.get("access_token") or "").strip(),
            "refresh_token": str(normalized_tokens.get("refresh_token") or "").strip(),
            "client_id": str(self.config.client_id or "").strip(),
        }
        account_id = self._extract_account_id(normalized_tokens)
        if account_id:
            payload["account_id"] = account_id
        session_token = str(normalized_tokens.get("session_token") or "").strip()
        if session_token:
            payload["session_token"] = session_token
        return payload

    def _build_headers(self) -> Dict[str, str]:
        """
        构造 Team 管理导入请求头。

        返回:
            Dict[str, str]: 请求头
            AI by zb
        """
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "X-API-Key": str(self.config.api_key or "").strip(),
        }

    @staticmethod
    def _summarize_response(response_data: Any, body: str) -> str:
        """
        生成不包含敏感字段的响应摘要。

        参数:
            response_data: JSON 响应
            body: 原始响应文本
        返回:
            str: 摘要
            AI by zb
        """
        if isinstance(response_data, dict):
            return json.dumps(
                {
                    "success": response_data.get("success"),
                    "code": response_data.get("code"),
                    "message": response_data.get("message"),
                    "error": response_data.get("error"),
                    "status": response_data.get("status"),
                },
                ensure_ascii=False,
            )
        return str(body or "")[:200]

    @staticmethod
    def _extract_error_message(response_data: Any, body: str, status_code: int) -> str:
        """
        从 Team 管理响应中提取可展示错误信息。

        参数:
            response_data: JSON 响应
            body: 原始响应文本
            status_code: HTTP 状态码
        返回:
            str: 错误信息
            AI by zb
        """
        if isinstance(response_data, dict):
            for key in ("error", "message", "detail", "status", "code"):
                value = response_data.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        fallback = str(body or "").strip()
        if fallback:
            return fallback[:500]
        return f"HTTP {status_code}"

    def import_single_account(self, email: str, tokens: Dict[str, Any]) -> bool:
        """
        上传单个母号到 Team 管理。

        参数:
            email: 账号邮箱
            tokens: OAuth token 字典
        返回:
            bool: 是否导入成功
            AI by zb
        """
        self.last_error_message = ""
        if not str(self.config.base_url or "").strip() or not str(self.config.api_key or "").strip():
            self.last_error_message = "Team 管理 API Key 未配置"
            return False
        payload = self.build_single_payload(email, tokens)
        if not payload.get("access_token") and not payload.get("session_token") and not payload.get("refresh_token"):
            self.last_error_message = "缺少可上传的 OAuth token"
            return False

        url = urljoin(f"{self.config.base_url.rstrip('/')}/", "admin/teams/import")
        headers = self._build_headers()
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=30,
                verify=False,
                allow_redirects=False,
            )
            if response.status_code in (301, 302, 307, 308):
                location = str(response.headers.get("Location") or "").strip()
                if location:
                    redirect_url = urljoin(url, location)
                    response = self.session.post(
                        redirect_url,
                        json=payload,
                        headers=headers,
                        timeout=30,
                        verify=False,
                        allow_redirects=False,
                    )
        except Exception as exc:
            self.last_error_message = str(exc)
            if self.logger:
                self.logger.warning("[TeamManage] 导入异常: %s | email=%s", exc, email)
            return False

        body = response.text
        try:
            response_data = response.json()
        except Exception:
            response_data = None

        ok = response.status_code in (200, 201) and not (
            isinstance(response_data, dict) and response_data.get("success") is False
        )
        if self.logger:
            if ok:
                self.logger.info("[TeamManage] 导入成功: %s | HTTP %s", email, response.status_code)
            else:
                self.last_error_message = self._extract_error_message(response_data, body, response.status_code)
                self.logger.warning(
                    "[TeamManage] 导入失败: %s | HTTP %s | error=%s | response=%s",
                    email,
                    response.status_code,
                    self.last_error_message,
                    self._summarize_response(response_data, body),
                )
        elif not ok:
            self.last_error_message = self._extract_error_message(response_data, body, response.status_code)
        return ok
