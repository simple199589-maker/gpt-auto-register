"""
邮箱服务模块
基于新的邮箱管理 API 实现临时邮箱功能
兼容旧业务对外函数签名
"""

import time
import email
import random
from datetime import datetime, timezone
from email import policy
from typing import Any, Dict, Optional

from app.config import (
    EMAIL_WORKER_URL,
    EMAIL_DOMAIN_INDEX,
    EMAIL_WAIT_TIMEOUT,
    EMAIL_POLL_INTERVAL,
    HTTP_TIMEOUT,
    EMAIL_ADMIN_PASSWORD
)
from app.utils import http_session, get_user_agent, extract_verification_code

MAILBOX_CONTEXT_PREFIX = "mailbox::"
GENERATE_LENGTH = 16
DEFAULT_EMAIL_LIMIT = 20


def _build_admin_headers():
    """
    构建邮箱服务管理员请求头。
    AI by zb
    """
    return {
        "User-Agent": get_user_agent(),
        "X-Admin-Token": EMAIL_ADMIN_PASSWORD
    }


def _request_email_api(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
):
    """
    统一发起邮箱服务请求。
    AI by zb
    """
    if not EMAIL_WORKER_URL:
        print("❌ 未配置邮箱服务地址: email.worker_url")
        return None

    if not EMAIL_ADMIN_PASSWORD:
        print("❌ 未配置邮箱服务管理员令牌: email.admin_password")
        return None

    try:
        return http_session.request(
            method=method,
            url=f"{EMAIL_WORKER_URL.rstrip('/')}{path}",
            headers=_build_admin_headers(),
            params=params,
            json=json_body,
            timeout=HTTP_TIMEOUT
        )
    except Exception as e:
        print(f"❌ 邮箱服务请求失败: {e}")
        return None


def _extract_email_api_error(response, fallback: str) -> str:
    """
    提取邮箱服务错误信息。
    AI by zb
    """
    if response is None:
        return fallback

    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        message = str(payload.get("error") or payload.get("message") or "").strip()
        if message:
            return message

    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text[:200]
    return fallback


def _absolute_email_service_url(url: str) -> str:
    """
    将邮箱服务返回的链接补全为绝对地址。
    AI by zb
    """
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return ""
    if normalized_url.startswith(("http://", "https://")):
        return normalized_url
    return f"{EMAIL_WORKER_URL.rstrip('/')}/{normalized_url.lstrip('/')}"


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
    发送单封邮件。

    参数:
        to_email: 收件邮箱
        subject: 邮件主题
        html: HTML 内容
        text: 纯文本内容
        from_email: 发件邮箱
        from_name: 发件人名称
        scheduled_at: 可选定时发送时间
    返回:
        Dict[str, Any]: 发送结果
        AI by zb
    """
    payload = {
        "from": str(from_email or "").strip() or "auth@joini.cloud",
        "fromName": str(from_name or "").strip() or "授权信息",
        "to": str(to_email or "").strip(),
        "subject": str(subject or "").strip(),
        "html": str(html or "").strip(),
        "text": str(text or "").strip(),
    }
    if scheduled_at:
        payload["scheduledAt"] = str(scheduled_at).strip()

    response = _request_email_api("POST", "/api/send", json_body=payload)
    if response is None:
        return {
            "success": False,
            "message": "发送邮件失败：邮箱服务无响应",
            "id": "",
        }

    if response.status_code not in {200, 201}:
        return {
            "success": False,
            "message": _extract_email_api_error(response, f"发送邮件失败：HTTP {response.status_code}"),
            "id": "",
        }

    try:
        result = response.json()
    except Exception as exc:
        return {
            "success": False,
            "message": f"发送邮件失败：响应解析异常 {exc}",
            "id": "",
        }

    if not isinstance(result, dict):
        return {
            "success": False,
            "message": "发送邮件失败：响应结构异常",
            "id": "",
        }

    succeeded = bool(result.get("success", True))
    return {
        "success": succeeded,
        "message": str(result.get("message") or ("邮件发送成功" if succeeded else "邮件发送失败")).strip(),
        "id": str(result.get("id") or "").strip(),
        "data": result,
    }


def create_temp_access_url(address: str) -> Dict[str, Any]:
    """
    为指定邮箱生成临时访问链接。

    参数:
        address: 邮箱地址
    返回:
        Dict[str, Any]: 临时访问结果
        AI by zb
    """
    response = _request_email_api(
        "POST",
        "/api/mailboxes/temp-access",
        json_body={"address": str(address or "").strip()},
    )
    if response is None:
        return {
            "success": False,
            "message": "生成临时访问链接失败：邮箱服务无响应",
            "url": "",
            "code": "",
        }

    if response.status_code not in {200, 201}:
        return {
            "success": False,
            "message": _extract_email_api_error(response, f"生成临时访问链接失败：HTTP {response.status_code}"),
            "url": "",
            "code": "",
        }

    try:
        result = response.json()
    except Exception as exc:
        return {
            "success": False,
            "message": f"生成临时访问链接失败：响应解析异常 {exc}",
            "url": "",
            "code": "",
        }

    if not isinstance(result, dict):
        return {
            "success": False,
            "message": "生成临时访问链接失败：响应结构异常",
            "url": "",
            "code": "",
        }

    url = _absolute_email_service_url(str(result.get("url") or "").strip())
    succeeded = bool(result.get("success")) and bool(url)
    return {
        "success": succeeded,
        "message": str(result.get("message") or ("临时访问链接已生成" if succeeded else "临时访问链接生成失败")).strip(),
        "url": url,
        "code": str(result.get("code") or "").strip(),
        "address": str(result.get("address") or address or "").strip(),
        "data": result,
    }


def _get_domain_index():
    """
    从配置的 `email.domainIndex` 中随机选择一个 domainIndex。
    AI by zb
    """
    configured_indexes = [int(item) for item in list(EMAIL_DOMAIN_INDEX or []) if str(item).strip().lstrip("-").isdigit()]
    if not configured_indexes:
        return None
    selected_index = random.choice(configured_indexes)
    print(f"📨 本次邮箱创建使用 domainIndex={selected_index}")
    return selected_index


def _resolve_mailbox_context(jwt_token: str):
    """
    从兼容令牌中解析邮箱地址。
    AI by zb
    """
    if not jwt_token:
        return None

    mailbox = str(jwt_token).strip()
    if mailbox.startswith(MAILBOX_CONTEXT_PREFIX):
        mailbox = mailbox[len(MAILBOX_CONTEXT_PREFIX):]

    return mailbox if "@" in mailbox else None


def _normalize_email_payload(payload: Dict[str, Any], mailbox: Optional[str] = None):
    """
    兼容新旧字段格式，统一邮件结构。
    AI by zb
    """
    normalized = dict(payload or {})
    sender = (
        normalized.get('sender') or
        normalized.get('from') or
        normalized.get('source') or
        ''
    )
    text_content = normalized.get('content') or normalized.get('text') or ''
    html_content = normalized.get('html_content') or normalized.get('html') or ''
    preview = normalized.get('preview') or text_content or html_content or ''

    normalized.setdefault('sender', sender)
    normalized.setdefault('from', sender)
    normalized.setdefault('source', sender)
    normalized.setdefault('text', text_content)
    normalized.setdefault('content', text_content)
    normalized.setdefault('html', html_content)
    normalized.setdefault('html_content', html_content)
    normalized.setdefault('body', preview)

    if mailbox:
        normalized.setdefault('mailbox', mailbox)

    return normalized


def _looks_like_openai_email(sender: str, subject: str, body: str = ""):
    """
    判断邮件是否疑似来自 OpenAI。
    AI by zb
    """
    content = f"{sender} {subject} {body}".lower()
    keywords = ["openai", "chatgpt"]
    return any(keyword in content for keyword in keywords)


def create_mailbox_marker() -> int:
    """
    创建邮箱轮询时间标记。

    @returns {int} 当前毫秒级时间戳
    @author AI by zb
    """
    return int(time.time() * 1000)


def _parse_timestamp_ms(value: Any):
    """
    将邮件时间字段解析为毫秒时间戳。

    @param {Any} value - 原始时间字段
    @returns {Optional[int]} 解析后的毫秒时间戳
    @author AI by zb
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

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
        except ValueError:
            continue

    return None


def _get_email_received_marker(email_item: Dict[str, Any]):
    """
    提取邮件接收时间标记。

    @param {Dict[str, Any]} email_item - 邮件数据
    @returns {Optional[int]} 邮件接收时间对应的毫秒时间戳
    @author AI by zb
    """
    candidates = [
        email_item.get("received_at_ms"),
        email_item.get("receivedAt"),
        email_item.get("received_at"),
        email_item.get("created_at"),
    ]

    for candidate in candidates:
        parsed = _parse_timestamp_ms(candidate)
        if parsed is not None:
            return parsed

    return None


def _build_valid_email_result(jwt_token: str, email_item: Dict[str, Any], with_detail: bool):
    """
    构造带时间标记的有效邮件结果。

    @param {str} jwt_token - 邮箱上下文令牌
    @param {Dict[str, Any]} email_item - 邮件列表项
    @param {bool} with_detail - 是否补拉详情
    @returns {Dict[str, Any]} 业务可直接使用的邮件结果
    @author AI by zb
    """
    result = dict(email_item or {})
    result["received_marker"] = _get_email_received_marker(email_item)

    if with_detail and email_item.get("id") is not None:
        detail = get_email_detail(jwt_token, str(email_item["id"]))
        if detail:
            result["detail"] = detail
            for field in (
                "sender",
                "from",
                "source",
                "subject",
                "verification_code",
                "content",
                "text",
                "html",
                "html_content",
                "body",
                "raw",
                "received_at",
                "created_at",
            ):
                if not result.get(field) and detail.get(field):
                    result[field] = detail.get(field)

            if result.get("received_marker") is None:
                result["received_marker"] = _get_email_received_marker(detail)

    return result


def fetch_valid_emails(jwt_token: str, since_marker: Optional[int] = None, with_detail: bool = True):
    """
    拉取当前时间线后的有效邮件，并返回新的时间标记。

    @param {str} jwt_token - 邮箱上下文令牌
    @param {Optional[int]} since_marker - 业务保存的上次时间标记
    @param {bool} with_detail - 是否补拉详情
    @returns {Dict[str, Any]} 包含有效邮件列表和 next_marker 的结果
    @author AI by zb
    """
    mailbox = _resolve_mailbox_context(jwt_token)
    if not mailbox:
        return {
            "success": False,
            "error": "无法从兼容令牌中解析邮箱地址"
        }

    request_marker = create_mailbox_marker()
    emails = fetch_emails(jwt_token) or []
    valid_items = []
    skipped_before_marker = 0
    skipped_without_timestamp = 0

    for email_item in emails:
        received_marker = _get_email_received_marker(email_item)

        if since_marker is not None and received_marker is None:
            skipped_without_timestamp += 1
            continue

        if since_marker is not None and received_marker < since_marker:
            skipped_before_marker += 1
            continue

        valid_items.append(_build_valid_email_result(jwt_token, email_item, with_detail))

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


def create_temp_email():
    """
    创建临时邮箱
    调用新邮箱服务的 /api/generate 接口
    
    返回:
        tuple: (邮箱地址, 兼容旧调用链的邮箱上下文令牌)，失败返回 (None, None)
    """
    print("📧 正在创建临时邮箱...")

    params = {
        "mode": "human",
        "length": GENERATE_LENGTH
    }
    domain_index = _get_domain_index()
    if domain_index is not None:
        params["domainIndex"] = domain_index

    response = _request_email_api("GET", "/api/generate", params=params)
    if response is None:
        return None, None

    if response.status_code != 200:
        print(f"❌ API 错误: HTTP {response.status_code}")
        print(f"   响应内容: {response.text[:200]}")
        return None, None

    try:
        result = response.json()
    except Exception as e:
        print(f"❌ 创建邮箱失败，响应解析异常: {e}")
        return None, None

    actual_email = result.get('email') or result.get('address')
    if actual_email:
        context_token = f"{MAILBOX_CONTEXT_PREFIX}{actual_email}"
        print(f"✅ 邮箱创建成功: {actual_email}")
        return actual_email, context_token

    print(f"⚠️ 响应中未包含邮箱地址: {result}")
    return None, None


def fetch_emails(jwt_token: str):
    """
    获取邮件列表
    
    参数:
        jwt_token: 创建邮箱时获得的 JWT 令牌
    
    返回:
        list: 邮件列表，失败返回 None
    """
    mailbox = _resolve_mailbox_context(jwt_token)
    if not mailbox:
        print("  获取邮件错误: 无法从兼容令牌中解析邮箱地址")
        return None

    response = _request_email_api(
        "GET",
        "/api/emails",
        params={
            "mailbox": mailbox,
            "limit": DEFAULT_EMAIL_LIMIT
        }
    )
    if response is None:
        return None

    if response.status_code != 200:
        print(f"  获取邮件错误: HTTP {response.status_code}")
        return None

    try:
        result = response.json()
    except Exception as e:
        print(f"  获取邮件错误: 响应解析失败: {e}")
        return None

    if isinstance(result, list):
        return [_normalize_email_payload(item, mailbox) for item in result]

    if isinstance(result, dict):
        emails = result.get('results', result.get('emails', []))
        if isinstance(emails, list):
            return [_normalize_email_payload(item, mailbox) for item in emails]

    print(f"  获取邮件错误: 响应格式异常: {result}")
    return None


def get_email_detail(jwt_token: str, email_id: str):
    """
    获取邮件详情
    
    参数:
        jwt_token: JWT 令牌
        email_id: 邮件 ID
    
    返回:
        dict: 邮件详情，失败返回 None
    """
    response = _request_email_api("GET", f"/api/email/{email_id}")
    if response is None:
        return None

    if response.status_code != 200:
        print(f"  获取邮件详情错误: HTTP {response.status_code}")
        return None

    try:
        detail = response.json()
    except Exception as e:
        print(f"  获取邮件详情错误: 响应解析失败: {e}")
        return None

    if isinstance(detail, dict):
        mailbox = _resolve_mailbox_context(jwt_token)
        return _normalize_email_payload(detail, mailbox)

    print(f"  获取邮件详情错误: 响应格式异常: {detail}")
    return None


def parse_raw_email(raw_content: str):
    """
    解析原始邮件内容
    
    参数:
        raw_content: 原始邮件字符串
    
    返回:
        dict: 包含 subject, body, sender 的字典
    """
    result = {'subject': '', 'body': '', 'sender': ''}
    
    if not raw_content:
        return result
    
    try:
        msg = email.message_from_string(raw_content, policy=policy.default)
        
        result['subject'] = msg.get('Subject', '')
        result['sender'] = msg.get('From', '')
        
        # 获取正文
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ['text/plain', 'text/html']:
                    payload = part.get_payload(decode=True)
                    if payload:
                        result['body'] = payload.decode('utf-8', errors='ignore')
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                result['body'] = payload.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  解析邮件错误: {e}")
    
    return result


def wait_for_verification_email(jwt_token: str, timeout: int = None):
    """
    等待并提取 OpenAI 验证码
    会持续轮询邮箱直到收到验证邮件或超时
    
    参数:
        jwt_token: JWT 令牌
        timeout: 超时时间（秒），默认使用配置文件中的值
    
    返回:
        str: 验证码，未找到返回 None
    """
    return wait_for_verification_email_with_marker(jwt_token, since_marker=None, timeout=timeout)


def wait_for_verification_email_with_marker(
    jwt_token: str,
    since_marker: Optional[int] = None,
    timeout: int = None
):
    """
    等待并提取指定时间线后的 OpenAI 验证码。

    @param {str} jwt_token - 邮箱上下文令牌
    @param {Optional[int]} since_marker - 起始时间标记，仅处理该时间线后的邮件
    @param {Optional[int]} timeout - 超时时间（秒）
    @returns {Optional[str]} 提取到的验证码
    @author AI by zb
    """
    if timeout is None:
        timeout = EMAIL_WAIT_TIMEOUT

    mailbox = _resolve_mailbox_context(jwt_token)
    if not mailbox:
        print("❌ 无法等待验证邮件：邮箱上下文无效")
        return None
    
    print(f"⏳ 正在等待验证邮件（最长 {timeout} 秒）...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        email_result = fetch_valid_emails(
            jwt_token,
            since_marker=since_marker,
            with_detail=True
        )

        if email_result.get("success") and email_result.get("emails"):
            for email_item in email_result["emails"]:
                raw_content = email_item.get('raw', '')
                subject = str(email_item.get('subject', '') or '')
                sender = str(
                    email_item.get('sender') or
                    email_item.get('from') or
                    email_item.get('source') or
                    ''
                ).lower()
                body = str(
                    email_item.get('body') or
                    email_item.get('content') or
                    email_item.get('text') or
                    email_item.get('html_content') or
                    email_item.get('preview') or
                    ''
                )
                verification_code = email_item.get('verification_code')

                if raw_content:
                    parsed = parse_raw_email(raw_content)
                    subject = parsed['subject'] or subject
                    sender = (parsed['sender'] or sender).lower()
                    body = parsed['body'] or body

                if not _looks_like_openai_email(sender, subject, body) and not verification_code:
                    detail = email_item.get("detail") or {}
                    detail_subject = str(detail.get('subject', '') or subject)
                    detail_body = str(
                        detail.get('html') or
                        detail.get('html_content') or
                        detail.get('text') or
                        detail.get('content') or
                        detail.get('body') or
                        body
                    )
                    detail_sender = str(
                        detail.get('sender') or
                        detail.get('from') or
                        detail.get('source') or
                        sender
                    ).lower()
                    detail_verification_code = detail.get('verification_code')

                    if not _looks_like_openai_email(detail_sender, detail_subject, detail_body) and not detail_verification_code:
                        continue

                    subject = detail_subject
                    body = detail_body
                    sender = detail_sender
                    verification_code = detail_verification_code or verification_code

                print(f"\n📧 收到 OpenAI 验证邮件!")
                print(f"   主题: {subject}")

                if verification_code:
                    print(f"  ✅ 提取到验证码: {verification_code}")
                    return str(verification_code)

                code = extract_verification_code(subject)
                if code:
                    return code

                if body:
                    code = extract_verification_code(body)
                    if code:
                        return code
        
        # 显示等待进度
        elapsed = int(time.time() - start_time)
        print(f"  等待中... ({elapsed}秒)", end='\r')
        time.sleep(EMAIL_POLL_INTERVAL)
    
    print("\n⏰ 等待验证邮件超时")
    return None
