"""
Outlook Mail Station 邮箱 provider。
AI by zb
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote

from app.config import (
    HTTP_TIMEOUT,
    OUTLOOK_API_KEY,
    OUTLOOK_AUTH_TYPE,
    OUTLOOK_BASE_URL,
    OUTLOOK_BATCH_CODE,
    OUTLOOK_DOMAIN,
    OUTLOOK_POLL_INTERVAL,
    OUTLOOK_REFRESH,
    OUTLOOK_SITE_CODE,
    OUTLOOK_WAIT_TIMEOUT,
)
from app.proxy import current_requests_proxies
from app.utils import extract_verification_code, get_user_agent, http_session

OUTLOOK_CONTEXT_PREFIX = "outlook::"
DEFAULT_EMAIL_LIMIT = 20


def _build_outlook_headers() -> Dict[str, str]:
    """
    构建 Outlook 开放接口请求头。

    返回:
        Dict[str, str]: 请求头
        AI by zb
    """
    headers = {"User-Agent": get_user_agent()}
    if str(OUTLOOK_AUTH_TYPE or "").strip().lower() == "bearer":
        headers["Authorization"] = f"Bearer {OUTLOOK_API_KEY}"
    else:
        headers["X-API-Key"] = OUTLOOK_API_KEY
    return headers


def _request_outlook_api(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
):
    """
    统一请求 Outlook Mail Station 开放接口。

    参数:
        method: HTTP 方法
        path: 接口路径
        params: 查询参数
        json_body: JSON 请求体
    返回:
        Response | None: HTTP 响应
        AI by zb
    """
    if not OUTLOOK_BASE_URL:
        print("❌ 未配置 Outlook API 地址: outlook.base_url")
        return None
    if not OUTLOOK_API_KEY:
        print("❌ 未配置 Outlook API Key: outlook.api_key")
        return None
    try:
        return http_session.request(
            method=method,
            url=f"{OUTLOOK_BASE_URL.rstrip('/')}{path}",
            headers=_build_outlook_headers(),
            params=params,
            json=json_body,
            timeout=HTTP_TIMEOUT,
            proxies=current_requests_proxies(),
        )
    except Exception as exc:
        print(f"❌ Outlook API 请求失败: {exc}")
        return None


def _extract_outlook_api_error(response, fallback: str) -> str:
    """
    提取 Outlook API 错误文案。

    参数:
        response: HTTP 响应
        fallback: 默认文案
    返回:
        str: 错误文案
        AI by zb
    """
    if response is None:
        return fallback
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        message = str(payload.get("detail") or payload.get("error") or payload.get("message") or "").strip()
        if message:
            return message
    text = str(getattr(response, "text", "") or "").strip()
    return text[:200] if text else fallback


def _resolve_mailbox_context(mailbox_context: str) -> Optional[str]:
    """
    从 Outlook 上下文解析邮箱地址。

    参数:
        mailbox_context: `outlook::email` 或邮箱地址
    返回:
        Optional[str]: 邮箱地址
        AI by zb
    """
    mailbox = str(mailbox_context or "").strip()
    if mailbox.startswith(OUTLOOK_CONTEXT_PREFIX):
        mailbox = mailbox[len(OUTLOOK_CONTEXT_PREFIX):]
    return mailbox if "@" in mailbox else None


def _parse_timestamp_ms(value: Any) -> Optional[int]:
    """
    将时间字段解析为毫秒时间戳。

    参数:
        value: 原始时间
    返回:
        Optional[int]: 毫秒时间戳
        AI by zb
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        value_int = int(value)
        return value_int if value_int > 10**11 else value_int * 1000
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        value_int = int(text)
        return value_int if value_int > 10**11 else value_int * 1000
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return None


def _normalize_outlook_message(payload: Dict[str, Any], mailbox: str = "") -> Dict[str, Any]:
    """
    将 Outlook 邮件结构转换为项目统一字段。

    参数:
        payload: Outlook 原始邮件
        mailbox: 邮箱地址
    返回:
        Dict[str, Any]: 标准邮件结构
        AI by zb
    """
    normalized = dict(payload or {})
    sender = (
        normalized.get("sender_email")
        or normalized.get("sender")
        or normalized.get("from")
        or normalized.get("source")
        or ""
    )
    subject = str(normalized.get("subject") or "")
    text_content = str(normalized.get("body_text") or normalized.get("content") or normalized.get("text") or "")
    html_content = str(normalized.get("body_html") or normalized.get("html_content") or normalized.get("html") or "")
    preview = str(normalized.get("preview") or text_content or html_content or "")
    received_at = str(normalized.get("sent_at") or normalized.get("received_at") or normalized.get("created_at") or "")
    code = str(normalized.get("verification_code") or "").strip()
    if not code:
        code = extract_verification_code(" ".join([subject, preview, text_content, html_content])) or ""

    normalized.setdefault("sender", sender)
    normalized.setdefault("from", sender)
    normalized.setdefault("source", sender)
    normalized.setdefault("content", text_content)
    normalized.setdefault("text", text_content)
    normalized.setdefault("html", html_content)
    normalized.setdefault("html_content", html_content)
    normalized.setdefault("body", preview)
    normalized.setdefault("preview", preview)
    normalized.setdefault("received_at", received_at)
    normalized.setdefault("created_at", received_at)
    normalized["received_marker"] = _parse_timestamp_ms(received_at)
    if code:
        normalized["verification_code"] = code
    if mailbox:
        normalized.setdefault("mailbox", mailbox)
    return normalized


def create_mailbox_marker() -> int:
    """
    创建邮箱轮询起始时间标记。

    返回:
        int: 毫秒级时间戳
        AI by zb
    """
    return int(time.time() * 1000)


def create_temp_email():
    """
    从 Outlook Mail Station 随机领取邮箱。

    返回:
        tuple[str | None, str | None]: 邮箱和上下文
        AI by zb
    """
    payload = {
        "site_code": str(OUTLOOK_SITE_CODE or "OPENAI").strip() or "OPENAI",
        "domain": str(OUTLOOK_DOMAIN or "").strip(),
    }
    if str(OUTLOOK_BATCH_CODE or "").strip():
        payload["batch_code"] = str(OUTLOOK_BATCH_CODE).strip()
    if not payload["domain"]:
        payload.pop("domain", None)

    response = _request_outlook_api("POST", "/api/open/random-email", json_body=payload)
    if response is None:
        return None, None
    if response.status_code not in {200, 201}:
        print(f"❌ Outlook 领取邮箱失败: {_extract_outlook_api_error(response, f'HTTP {response.status_code}')}")
        return None, None
    try:
        result = response.json()
    except Exception as exc:
        print(f"❌ Outlook 领取邮箱响应解析失败: {exc}")
        return None, None
    email = str((result or {}).get("email") or (result or {}).get("address") or "").strip()
    if not email:
        print(f"⚠️ Outlook 领取邮箱响应未包含 email: {result}")
        return None, None
    return email, f"{OUTLOOK_CONTEXT_PREFIX}{email}"


def fetch_emails(mailbox_context: str):
    """
    拉取 Outlook 邮件列表。

    参数:
        mailbox_context: Outlook 上下文或邮箱地址
    返回:
        list[dict] | None: 邮件列表
        AI by zb
    """
    mailbox = _resolve_mailbox_context(mailbox_context)
    if not mailbox:
        print("  Outlook 获取邮件错误: 邮箱上下文无效")
        return None
    response = _request_outlook_api(
        "GET",
        f"/api/open/mailboxes/{quote(mailbox, safe='')}/messages",
        params={"refresh": str(bool(OUTLOOK_REFRESH)).lower(), "folder": "inbox"},
    )
    if response is None:
        return None
    if response.status_code != 200:
        print(f"  Outlook 获取邮件错误: {_extract_outlook_api_error(response, f'HTTP {response.status_code}')}")
        return None
    try:
        result = response.json()
    except Exception as exc:
        print(f"  Outlook 获取邮件响应解析失败: {exc}")
        return None
    items = result if isinstance(result, list) else (result or {}).get("items") or (result or {}).get("messages") or []
    if not isinstance(items, list):
        print(f"  Outlook 获取邮件响应格式异常: {result}")
        return None
    return [_normalize_outlook_message(item, mailbox) for item in items[:DEFAULT_EMAIL_LIMIT]]


def get_email_detail(mailbox_context: str, email_id: str):
    """
    拉取 Outlook 邮件详情。

    参数:
        mailbox_context: Outlook 上下文或邮箱地址
        email_id: 邮件 ID
    返回:
        dict | None: 邮件详情
        AI by zb
    """
    mailbox = _resolve_mailbox_context(mailbox_context)
    if not mailbox:
        return None
    response = _request_outlook_api(
        "GET",
        f"/api/open/mailboxes/{quote(mailbox, safe='')}/messages/{quote(str(email_id), safe='')}",
        params={"refresh": str(bool(OUTLOOK_REFRESH)).lower()},
    )
    if response is None or response.status_code != 200:
        return None
    try:
        detail = response.json()
    except Exception:
        return None
    if isinstance(detail, dict):
        return _normalize_outlook_message(detail.get("message") or detail, mailbox)
    return None


def fetch_valid_emails(mailbox_context: str, since_marker: Optional[int] = None, with_detail: bool = True):
    """
    拉取有效 Outlook 邮件并按时间标记过滤。

    参数:
        mailbox_context: Outlook 上下文或邮箱地址
        since_marker: 起始时间标记
        with_detail: 是否补拉详情
    返回:
        dict: 标准结果
        AI by zb
    """
    mailbox = _resolve_mailbox_context(mailbox_context)
    if not mailbox:
        return {"success": False, "error": "无法从 Outlook 上下文中解析邮箱地址"}
    request_marker = create_mailbox_marker()
    emails = fetch_emails(mailbox_context) or []
    valid_items = []
    skipped_before_marker = 0
    skipped_without_timestamp = 0
    for item in emails:
        received_marker = item.get("received_marker") or _parse_timestamp_ms(
            item.get("received_at") or item.get("created_at")
        )
        if since_marker is not None and received_marker is None:
            skipped_without_timestamp += 1
            continue
        if since_marker is not None and received_marker < since_marker:
            skipped_before_marker += 1
            continue
        if with_detail and item.get("id") is not None:
            detail = get_email_detail(mailbox_context, str(item["id"]))
            if detail:
                merged = dict(item)
                merged.update({key: value for key, value in detail.items() if value not in ("", None)})
                item = merged
        valid_items.append(item)
    valid_items.sort(key=lambda item: item.get("received_marker") or 0, reverse=True)
    return {
        "success": True,
        "mailbox": mailbox,
        "since_marker": since_marker,
        "next_marker": request_marker,
        "total_count": len(emails),
        "valid_count": len(valid_items),
        "skipped_before_marker": skipped_before_marker,
        "skipped_without_timestamp": skipped_without_timestamp,
        "emails": valid_items,
    }


def send_single_email(
    to_email: str,
    subject: str,
    html: str,
    text: str,
    from_email: str = "auth@joini.cloud",
    from_name: str = "授权信息",
    scheduled_at: str = "",
) -> Dict[str, Any]:
    """
    返回 Outlook 开放接口发信能力边界。

    参数:
        to_email: 收件邮箱
        subject: 邮件主题
        html: HTML 内容
        text: 纯文本内容
        from_email: 发件邮箱
        from_name: 发件人名称
        scheduled_at: 定时发送时间
    返回:
        Dict[str, Any]: 不支持结果
        AI by zb
    """
    return {
        "success": False,
        "message": "Outlook API 未提供发送接口",
        "id": "",
        "data": {
            "to": str(to_email or "").strip(),
            "subject": str(subject or "").strip(),
            "from": str(from_email or "").strip(),
            "fromName": str(from_name or "").strip(),
            "scheduledAt": str(scheduled_at or "").strip(),
        },
    }


__all__ = [
    "OUTLOOK_CONTEXT_PREFIX",
    "create_mailbox_marker",
    "create_temp_email",
    "fetch_emails",
    "fetch_valid_emails",
    "get_email_detail",
    "send_single_email",
]
