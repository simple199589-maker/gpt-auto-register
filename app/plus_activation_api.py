"""
Plus / Team 激活接口流程。
AI by zb
"""

from __future__ import annotations

import json
import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import cfg
from app.utils import create_http_session, get_user_agent


AUTH_SESSION_URL = "https://chatgpt.com/api/auth/session"
PLUS_RESULT_CACHE_TTL_SECONDS = 120
ACTIVATION_SUBMIT_TIMEOUT_SECONDS = 120
ACTIVATION_TIMEOUT_STATUS_POLL_SECONDS = 120
ACCESS_TOKEN_FETCH_MAX_ATTEMPTS = 5
ACCESS_TOKEN_FETCH_RETRY_INTERVAL_SECONDS = 2
_PLUS_RESULT_CACHE: Dict[str, Dict[str, Any]] = {}
_PLUS_RESULT_CACHE_LOCK = threading.Lock()


@dataclass
class PlusActivationResult:
    """
    Plus 激活流程结果。

    AI by zb
    """

    success: bool
    stage: str
    accepted: bool = False
    access_token: str = ""
    request_id: str = ""
    status: str = ""
    message: str = ""
    response_data: Dict[str, Any] = field(default_factory=dict)
    session_info: Dict[str, Any] = field(default_factory=dict)


class ManualActivationCancelledError(RuntimeError):
    """
    手动激活流程已收到取消请求。

    AI by zb
    """


def _ensure_activation_not_cancelled(
    should_cancel: Optional[Callable[[], bool]],
    action_label: str,
) -> None:
    """
    检查当前激活流程是否已收到取消请求。

    参数:
        should_cancel: 取消检查函数
        action_label: 激活类型显示名称
    返回:
        None
        AI by zb
    """
    if should_cancel and should_cancel():
        raise ManualActivationCancelledError(f"{action_label}已取消")


def _cache_key_for_access_token(access_token: str, cache_scope: str = "plus") -> str:
    """
    生成 accessToken 的缓存键，避免在内存中直接保存明文 token。

    参数:
        access_token: ChatGPT accessToken
        cache_scope: 缓存作用域
    返回:
        str: 哈希后的缓存键
        AI by zb
    """
    normalized_scope = str(cache_scope or "plus").strip().lower()
    normalized_token = f"{normalized_scope}:{str(access_token or '').strip()}".encode("utf-8")
    return hashlib.sha256(normalized_token).hexdigest()


def _clone_plus_result(result: PlusActivationResult) -> PlusActivationResult:
    """
    复制 Plus 激活结果，避免缓存对象被外部意外修改。

    参数:
        result: 原始结果
    返回:
        PlusActivationResult: 复制结果
        AI by zb
    """
    return PlusActivationResult(
        success=result.success,
        stage=result.stage,
        accepted=result.accepted,
        access_token=result.access_token,
        request_id=result.request_id,
        status=result.status,
        message=result.message,
        response_data=dict(result.response_data or {}),
        session_info=dict(result.session_info or {}),
    )


def _get_cached_plus_result(access_token: str, cache_scope: str = "plus") -> Optional[PlusActivationResult]:
    """
    获取短时间内同一 accessToken 的激活缓存结果。

    参数:
        access_token: ChatGPT accessToken
        cache_scope: 缓存作用域
    返回:
        Optional[PlusActivationResult]: 缓存结果
        AI by zb
    """
    cache_key = _cache_key_for_access_token(access_token, cache_scope=cache_scope)
    now = time.time()
    with _PLUS_RESULT_CACHE_LOCK:
        expired_keys = [
            key
            for key, item in _PLUS_RESULT_CACHE.items()
            if now - float(item.get("created_at", 0)) > PLUS_RESULT_CACHE_TTL_SECONDS
        ]
        for key in expired_keys:
            _PLUS_RESULT_CACHE.pop(key, None)

        cached = _PLUS_RESULT_CACHE.get(cache_key)
        if not cached:
            return None
        result = cached.get("result")
        if not isinstance(result, PlusActivationResult):
            _PLUS_RESULT_CACHE.pop(cache_key, None)
            return None
        return _clone_plus_result(result)


def _set_cached_plus_result(access_token: str, result: PlusActivationResult, cache_scope: str = "plus") -> None:
    """
    写入 Plus 激活结果缓存。

    参数:
        access_token: ChatGPT accessToken
        result: 激活结果
        cache_scope: 缓存作用域
    返回:
        None
        AI by zb
    """
    cache_key = _cache_key_for_access_token(access_token, cache_scope=cache_scope)
    with _PLUS_RESULT_CACHE_LOCK:
        _PLUS_RESULT_CACHE[cache_key] = {
            "created_at": time.time(),
            "result": _clone_plus_result(result),
        }


def _coerce_activation_success_flag(value: Any) -> Optional[bool]:
    """
    将接口返回的 success 字段解析为布尔值。

    参数:
        value: success 原始值
    返回:
        Optional[bool]: 解析结果；无法判断时返回 None
        AI by zb
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return None

    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "ok", "success", "succeeded", "completed", "done"}:
        return True
    if normalized in {"0", "false", "no", "fail", "failed", "error", "cancelled", "canceled"}:
        return False
    return None


def _infer_activation_success(final_data: Dict[str, Any]) -> bool:
    """
    按任务查询接口标准字段判断当前激活是否最终成功。

    参数:
        final_data: 激活接口返回数据
    返回:
        bool: 是否成功
        AI by zb
    """
    explicit_success = _coerce_activation_success_flag((final_data or {}).get("success"))
    state = str((final_data or {}).get("state") or "").strip().lower()
    status = str((final_data or {}).get("status") or "").strip().lower()
    return state == "completed" and explicit_success is True and status == "success"


def _is_cancelled_activation_result(final_data: Optional[Dict[str, Any]]) -> bool:
    """
    判断任务快照是否属于已取消终态。

    参数:
        final_data: 激活接口返回数据
    返回:
        bool: 是否已取消
        AI by zb
    """
    if not isinstance(final_data, dict):
        return False
    state = str(final_data.get("state") or "").strip().lower()
    status = str(final_data.get("status") or "").strip().lower()
    return state in {"cancelled", "canceled"} or status in {"cancelled", "canceled"}


def _extract_request_id(data: Optional[Dict[str, Any]]) -> str:
    """
    从接口返回中提取 requestId。

    参数:
        data: 接口返回数据
    返回:
        str: requestId
        AI by zb
    """
    if not isinstance(data, dict):
        return ""

    direct_request_id = str(data.get("requestId") or data.get("request_id") or "").strip()
    if direct_request_id:
        return direct_request_id

    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        return str(nested_data.get("requestId") or nested_data.get("request_id") or "").strip()
    return ""


def _normalize_activation_state(data: Optional[Dict[str, Any]]) -> str:
    """
    规范化激活任务状态字段。

    参数:
        data: 接口返回数据
    返回:
        str: 标准化后的状态
        AI by zb
    """
    if not isinstance(data, dict):
        return ""
    return str(data.get("state") or data.get("status") or "").strip().lower()


def _collect_activation_response_text(data: Optional[Dict[str, Any]]) -> str:
    """
    汇总激活接口返回中的状态文案，便于统一识别中间态关键词。

    参数:
        data: 接口返回数据
    返回:
        str: 小写后的合并文本
        AI by zb
    """
    if not isinstance(data, dict):
        return ""

    text_parts = [
        str(data.get("message") or "").strip(),
        str(data.get("rawMessage") or "").strip(),
        str(data.get("status") or "").strip(),
        str(data.get("state") or "").strip(),
    ]
    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        text_parts.extend(
            [
                str(nested_data.get("message") or "").strip(),
                str(nested_data.get("rawMessage") or "").strip(),
                str(nested_data.get("status") or "").strip(),
                str(nested_data.get("state") or "").strip(),
            ]
        )
    return " ".join(part for part in text_parts if part).strip().lower()


def _is_terminal_activation_state(state: str) -> bool:
    """
    判断激活任务状态是否已进入终态。

    参数:
        state: 标准化状态值
    返回:
        bool: 是否终态
        AI by zb
    """
    return state in {"completed", "success", "succeeded", "done", "failed", "cancelled", "canceled"}


def _is_processing_activation_response(data: Optional[Dict[str, Any]]) -> bool:
    """
    判断激活提交响应是否属于“请求已受理，等待后续轮询”的中间态。

    参数:
        data: 激活提交接口响应
    返回:
        bool: 是否为处理中中间态
        AI by zb
    """
    if not isinstance(data, dict):
        return False

    normalized_state = _normalize_activation_state(data)
    if _is_terminal_activation_state(normalized_state):
        return False

    combined_text = _collect_activation_response_text(data)
    failure_keywords = (
        "失败",
        "错误",
        "异常",
        "取消",
        "已取消",
        "拒绝",
        "无效",
        "失效",
        "过期",
        "退回",
        "重试",
        "重新获取",
        "token 无效",
        "token无效",
        "fail",
        "failed",
        "error",
        "cancelled",
        "canceled",
        "denied",
        "invalid",
    )
    processing_keywords = (
        "已收到请求",
        "正在生成",
        "生成支付链接",
        "正在处理",
        "处理中",
        "当前状态",
        "次查询",
        "请稍候",
        "请等待",
        "稍候",
        "等待",
        "排队",
        "队列",
        "received",
        "accepted",
        "processing",
        "pending",
        "queued",
        "queue",
        "running",
        "working",
        "in progress",
        "request received",
    )

    if any(keyword in combined_text for keyword in failure_keywords):
        return False
    if any(keyword in combined_text for keyword in processing_keywords):
        return True
    return False


def _build_activation_result_from_snapshot(
    action_label: str,
    access_token: str,
    request_id: str,
    snapshot_data: Optional[Dict[str, Any]] = None,
    accepted: bool = False,
) -> PlusActivationResult:
    """
    基于激活任务快照构造统一结果对象。

    参数:
        action_label: 激活类型显示名称
        access_token: ChatGPT accessToken
        request_id: 激活任务 requestId
        snapshot_data: 任务状态快照
        accepted: 是否已确认请求提交成功
    返回:
        PlusActivationResult: 统一结果对象
        AI by zb
    """
    normalized_snapshot = dict(snapshot_data or {})
    normalized_state = _normalize_activation_state(normalized_snapshot)
    is_terminal = _is_terminal_activation_state(normalized_state)
    is_cancelled = _is_cancelled_activation_result(normalized_snapshot)
    is_completed = is_terminal and not is_cancelled and _infer_activation_success(normalized_snapshot)

    if is_completed:
        stage = "completed"
    elif is_cancelled:
        stage = "cancelled"
    elif is_terminal:
        stage = "activate"
    elif accepted:
        stage = "submitted"
    else:
        stage = "activate"

    status_text = str(normalized_snapshot.get("status") or normalized_snapshot.get("state") or "").strip()
    if not status_text:
        if stage == "submitted":
            status_text = "处理中"
        elif stage == "completed":
            status_text = "success"
        elif stage == "cancelled":
            status_text = "cancelled"
        elif normalized_state:
            status_text = normalized_state
        else:
            status_text = "unknown"

    message_text = str(
        normalized_snapshot.get("message")
        or normalized_snapshot.get("rawMessage")
        or ""
    ).strip()
    if not message_text:
        if stage == "submitted":
            message_text = f"{action_label}激活请求已提交"
        elif stage == "completed":
            message_text = f"{action_label}激活成功"
        elif stage == "cancelled":
            message_text = f"{action_label}激活已取消"
        elif is_terminal:
            message_text = f"{action_label}激活失败"

    accepted_flag = bool(is_completed or (accepted and stage == "submitted"))

    return PlusActivationResult(
        success=is_completed,
        stage=stage,
        accepted=accepted_flag,
        access_token=access_token,
        request_id=str(request_id or "").strip(),
        status=status_text,
        message=message_text,
        response_data=normalized_snapshot,
    )


def _build_submitted_activation_result(
    action_label: str,
    access_token: str,
    request_id: str,
    submit_data: Optional[Dict[str, Any]] = None,
) -> PlusActivationResult:
    """
    基于激活提交响应构造“已提交待处理”的结果对象。

    参数:
        action_label: 激活类型显示名称
        access_token: ChatGPT accessToken
        request_id: 激活任务 requestId
        submit_data: 激活提交接口响应
    返回:
        PlusActivationResult: 已提交结果
        AI by zb
    """
    normalized_submit_data = dict(submit_data or {})
    normalized_state = _normalize_activation_state(normalized_submit_data)
    if _is_terminal_activation_state(normalized_state):
        terminal_success = _infer_activation_success(normalized_submit_data)
        return _build_activation_result_from_snapshot(
            action_label=action_label,
            access_token=access_token,
            request_id=request_id,
            snapshot_data=normalized_submit_data,
            accepted=terminal_success,
        )

    accepted = _is_processing_activation_response(normalized_submit_data)
    if not accepted:
        status_text = "unknown"
        message_text = str(
            normalized_submit_data.get("message")
            or normalized_submit_data.get("rawMessage")
            or ""
        ).strip() or f"{action_label}激活请求未被受理"
        return PlusActivationResult(
            success=False,
            stage="activate",
            accepted=False,
            access_token=access_token,
            request_id=str(request_id or "").strip(),
            status=status_text,
            message=message_text,
            response_data=normalized_submit_data,
        )

    status_text = str(
        normalized_submit_data.get("status")
        or normalized_submit_data.get("state")
        or ""
    ).strip() or "处理中"
    message_text = str(
        normalized_submit_data.get("message")
        or normalized_submit_data.get("rawMessage")
        or ""
    ).strip() or f"{action_label}激活请求已提交"

    return PlusActivationResult(
        success=False,
        stage="submitted",
        accepted=True,
        access_token=access_token,
        request_id=str(request_id or "").strip(),
        status=status_text,
        message=message_text,
        response_data=normalized_submit_data,
    )


def _summarize_activation_snapshot(snapshot_data: Optional[Dict[str, Any]]) -> str:
    """
    提取激活任务快照里的核心判定字段，便于日志输出。

    参数:
        snapshot_data: 任务状态快照
    返回:
        str: 摘要文本
        AI by zb
    """
    data = dict(snapshot_data or {})
    state_text = str(data.get("state") or "").strip() or "unknown"
    success_value = data.get("success")
    success_text = "null" if success_value is None else str(success_value).strip()
    status_text = str(data.get("status") or "").strip() or "unknown"
    return f"state={state_text} success={success_text} status={status_text}"


def _is_pending_activation_result(result: PlusActivationResult) -> bool:
    """
    判断当前激活结果是否仍处于已提交待轮询状态。

    参数:
        result: 激活结果
    返回:
        bool: 是否仍需继续轮询
        AI by zb
    """
    return (
        isinstance(result, PlusActivationResult)
        and not bool(result.success)
        and bool(result.accepted)
        and str(result.stage or "").strip().lower() == "submitted"
    )


def _ensure_chatgpt_origin(driver) -> None:
    """
    确保浏览器上下文位于 chatgpt.com 域名下，便于复用当前登录态读取 session。

    参数:
        driver: Selenium WebDriver
    返回:
        None
        AI by zb
    """
    current_url = str(getattr(driver, "current_url", "") or "")
    if "chatgpt.com" in current_url:
        return

    print("🌐 当前页面不在 chatgpt.com，正在切换到主页以读取 session...")
    driver.get("https://chatgpt.com")
    time.sleep(3)


def _fetch_auth_session_via_browser_fetch(driver) -> Dict[str, Any]:
    """
    通过浏览器页面上下文内的 fetch 直接拉取 auth/session 数据。

    参数:
        driver: Selenium WebDriver
    返回:
        Dict[str, Any]: session JSON
        AI by zb
    """
    _ensure_chatgpt_origin(driver)
    result = driver.execute_async_script(
        """
        const callback = arguments[arguments.length - 1];
        const url = arguments[0];
        fetch(url, {
            method: 'GET',
            credentials: 'include',
            headers: { 'accept': 'application/json' }
        })
            .then(async (response) => {
                const text = await response.text();
                let data = null;
                try {
                    data = JSON.parse(text);
                } catch (error) {
                    callback({
                        ok: false,
                        status: response.status,
                        error: `JSON parse failed: ${error}`,
                        text
                    });
                    return;
                }
                callback({
                    ok: response.ok,
                    status: response.status,
                    data
                });
            })
            .catch((error) => {
                callback({
                    ok: false,
                    status: 0,
                    error: String(error)
                });
            });
        """,
        AUTH_SESSION_URL,
    )

    if not isinstance(result, dict):
        raise RuntimeError("浏览器 fetch 返回的 session 数据格式异常")

    if not result.get("ok"):
        raise RuntimeError(
            f"浏览器 fetch 读取 auth/session 失败: HTTP {result.get('status', 0)} | {result.get('error') or result.get('text', '')[:200]}"
        )

    data = result.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("浏览器 fetch 读取 auth/session 成功，但返回数据不是 JSON 对象")
    return data


def _fetch_auth_session_via_browser_url(driver) -> Dict[str, Any]:
    """
    通过浏览器直接打开 auth/session 页面并读取正文 JSON。

    参数:
        driver: Selenium WebDriver
    返回:
        Dict[str, Any]: session JSON
        AI by zb
    """
    _ensure_chatgpt_origin(driver)
    origin_handle = str(getattr(driver, "current_window_handle", "") or "")
    opened_temp_tab = False

    def _read_page_json(timeout_seconds: int = 10) -> Dict[str, Any]:
        """
        读取当前页面正文中的 JSON 文本并解析。

        参数:
            timeout_seconds: 最大等待秒数
        返回:
            Dict[str, Any]: 页面中的 JSON 对象
            AI by zb
        """
        deadline = time.time() + max(int(timeout_seconds or 10), 1)
        last_text = ""
        last_error = ""

        while time.time() < deadline:
            try:
                text = str(
                    driver.execute_script(
                        """
                        const pre = document.querySelector('pre');
                        const bodyText = document.body ? (document.body.innerText || document.body.textContent || '') : '';
                        const preText = pre ? (pre.innerText || pre.textContent || '') : '';
                        const rootText = document.documentElement
                            ? (document.documentElement.innerText || document.documentElement.textContent || '')
                            : '';
                        return (preText || bodyText || rootText || '').trim();
                        """
                    )
                    or ""
                ).strip()
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.5)
                continue

            if not text:
                time.sleep(0.5)
                continue

            last_text = text
            try:
                data = json.loads(text)
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.5)
                continue

            if not isinstance(data, dict):
                raise RuntimeError("浏览器地址栏读取 auth/session 成功，但返回数据不是 JSON 对象")
            return data

        if last_text:
            raise RuntimeError(
                f"浏览器地址栏读取 auth/session 失败，页面内容无法解析为 JSON: {last_text[:200]}"
            )
        raise RuntimeError(
            f"浏览器地址栏读取 auth/session 失败，未读取到页面正文"
            + (f" | {last_error}" if last_error else "")
        )

    try:
        print(f"🌐 正在通过浏览器标签页打开 {AUTH_SESSION_URL}")
        driver.switch_to.new_window("tab")
        opened_temp_tab = True
        driver.get(AUTH_SESSION_URL)
        return _read_page_json()
    finally:
        if opened_temp_tab:
            try:
                driver.close()
            except Exception:
                pass

        if origin_handle:
            try:
                if origin_handle in driver.window_handles:
                    driver.switch_to.window(origin_handle)
            except Exception:
                pass


def _fetch_auth_session_with_fallback(driver) -> Dict[str, Any]:
    """
    以“浏览器 fetch 优先，地址栏直读降级”为策略获取 auth/session。

    参数:
        driver: Selenium WebDriver
    返回:
        Dict[str, Any]: session JSON
        AI by zb
    """
    errors = []

    try:
        print("🔑 正在尝试浏览器 fetch 方式读取 auth/session...")
        return _fetch_auth_session_via_browser_fetch(driver)
    except Exception as exc:
        errors.append(f"browser_fetch={exc}")
        print(f"⚠️ 浏览器 fetch 读取 auth/session 失败，降级为地址栏直读: {exc}")

    try:
        print("🔑 正在尝试浏览器地址栏读取 auth/session...")
        return _fetch_auth_session_via_browser_url(driver)
    except Exception as exc:
        errors.append(f"browser_url={exc}")
        raise RuntimeError("；".join(errors)) from exc


def fetch_access_token(driver) -> str:
    """
    从当前浏览器登录态中提取 accessToken。

    参数:
        driver: Selenium WebDriver
    返回:
        str: accessToken
        AI by zb
    """
    print("🔑 正在提取 accessToken...")
    last_error = ""

    for attempt in range(1, ACCESS_TOKEN_FETCH_MAX_ATTEMPTS + 1):
        try:
            session_data = _fetch_auth_session_with_fallback(driver)
        except Exception as exc:
            last_error = str(exc)
            if attempt < ACCESS_TOKEN_FETCH_MAX_ATTEMPTS:
                print(
                    f"⏳ 第 {attempt}/{ACCESS_TOKEN_FETCH_MAX_ATTEMPTS} 次提取 accessToken 失败，"
                    f"{ACCESS_TOKEN_FETCH_RETRY_INTERVAL_SECONDS} 秒后重试: {last_error}"
                )
                time.sleep(ACCESS_TOKEN_FETCH_RETRY_INTERVAL_SECONDS)
                continue
            raise RuntimeError(last_error) from exc

        access_token = str(session_data.get("accessToken") or "").strip()
        if access_token:
            print("✅ 已成功提取 accessToken")
            return access_token

        session_keys = ",".join(sorted(map(str, session_data.keys()))) if isinstance(session_data, dict) else ""
        last_error = (
            "auth/session 中未找到 accessToken 字段"
            + (f"（当前字段: {session_keys}）" if session_keys else "")
        )
        if attempt < ACCESS_TOKEN_FETCH_MAX_ATTEMPTS:
            print(
                f"⏳ 第 {attempt}/{ACCESS_TOKEN_FETCH_MAX_ATTEMPTS} 次未拿到 accessToken，"
                f"{ACCESS_TOKEN_FETCH_RETRY_INTERVAL_SECONDS} 秒后重试"
            )
            time.sleep(ACCESS_TOKEN_FETCH_RETRY_INTERVAL_SECONDS)
            continue

    raise RuntimeError(last_error or "auth/session 中未找到 accessToken 字段")


def fetch_session_info(driver) -> Dict[str, Any]:
    """
    从当前浏览器登录态提取可复用的会话摘要信息。

    参数:
        driver: Selenium WebDriver
    返回:
        Dict[str, Any]: 会话摘要
        AI by zb
    """
    session_data = _fetch_auth_session_with_fallback(driver)

    account = session_data.get("account") if isinstance(session_data.get("account"), dict) else {}
    user = session_data.get("user") if isinstance(session_data.get("user"), dict) else {}
    return {
        "expires": str(session_data.get("expires") or ""),
        "authProvider": str(session_data.get("authProvider") or ""),
        "sessionToken": str(session_data.get("sessionToken") or ""),
        "accountId": str(account.get("id") or account.get("account_id") or ""),
        "userId": str(user.get("id") or user.get("sub") or ""),
    }


def _wait_for_page_stable_before_fetch(
    driver,
    timeout_seconds: int = 10,
    poll_interval_seconds: float = 0.5,
) -> None:
    """
    在提取会话信息前等待页面进入稳定状态。

    参数:
        driver: Selenium WebDriver
        timeout_seconds: 最大等待秒数
        poll_interval_seconds: 轮询间隔秒数
    返回:
        None
        AI by zb
    """
    deadline = time.time() + max(int(timeout_seconds or 10), 1)
    last_state = ""

    while time.time() < deadline:
        try:
            last_state = str(driver.execute_script("return document.readyState") or "").strip().lower()
        except Exception as exc:
            last_state = f"error:{exc}"
            time.sleep(max(float(poll_interval_seconds or 0.5), 0.1))
            continue

        if last_state == "complete":
            print("✅ 页面已稳定，开始提取 accessToken")
            return

        time.sleep(max(float(poll_interval_seconds or 0.5), 0.1))

    print(f"⚠️ 等待页面稳定超时，继续尝试提取 accessToken: readyState={last_state or 'unknown'}")


def _build_activation_headers() -> Dict[str, str]:
    """
    构建激活接口请求头。

    返回:
        Dict[str, str]: 请求头
        AI by zb
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": get_user_agent(),
    }
    api_key = str(cfg.activation_api.api_key or "").strip()
    bearer = str(cfg.activation_api.bearer or "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _validate_activation_config() -> None:
    """
    校验激活接口配置是否完整。

    返回:
        None
        AI by zb
    """
    base_url = str(cfg.activation_api.base_url or "").strip()
    api_key = str(cfg.activation_api.api_key or "").strip()
    bearer = str(cfg.activation_api.bearer or "").strip()

    if not base_url:
        raise RuntimeError("activation_api.base_url 未配置")
    if not api_key and not bearer:
        raise RuntimeError("activation_api.api_key 或 activation_api.bearer 至少需要配置一个")


def _create_single_submit_session() -> requests.Session:
    """
    创建用于提交激活请求的单发 Session，禁用自动重试，避免 POST 被重复提交。

    返回:
        requests.Session: 禁用自动重试的会话
        AI by zb
    """
    session = requests.Session()
    retry_strategy = Retry(total=0, connect=0, read=0, redirect=0, status=0)
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _request_json(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    调用激活服务并返回 JSON 响应。

    参数:
        method: HTTP 方法
        path: 接口路径
        payload: JSON 请求体
    返回:
        Dict[str, Any]: 响应 JSON
        AI by zb
    """
    session = create_http_session()
    url = f"{str(cfg.activation_api.base_url).rstrip('/')}{path}"
    response = session.request(
        method=method.upper(),
        url=url,
        json=payload,
        headers=_build_activation_headers(),
        timeout=30,
    )

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(
            f"接口返回非 JSON: HTTP {response.status_code} | {response.text[:200]}"
        ) from exc

    if not response.ok:
        raise RuntimeError(
            f"接口调用失败: HTTP {response.status_code} | {data.get('message') or data.get('errorMessage') or response.text[:200]}"
        )

    if not isinstance(data, dict):
        raise RuntimeError("接口返回 JSON 不是对象结构")

    return data


def get_service_status() -> Dict[str, Any]:
    """
    获取激活服务当前状态。

    返回:
        Dict[str, Any]: ServiceStatusResponse
        AI by zb
    """
    return _request_json("GET", "/api/v1/status")


def get_request_status(request_id: str) -> Dict[str, Any]:
    """
    查询指定激活任务的当前状态。

    参数:
        request_id: 任务请求 ID
    返回:
        Dict[str, Any]: RequestStatusResponse
        AI by zb
    """
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise RuntimeError("缺少 requestId，无法查询激活任务状态")
    return _request_json("GET", f"/api/v1/requests/{normalized_request_id}")


def query_activation_request_result(
    request_id: str,
    action_label: str = "激活",
    access_token: str = "",
) -> PlusActivationResult:
    """
    查询指定激活任务，并转换为统一结果对象。

    参数:
        request_id: 任务请求 ID
        action_label: 激活类型显示名称
        access_token: 可选的 accessToken
    返回:
        PlusActivationResult: 统一结果对象
        AI by zb
    """
    status_data = get_request_status(request_id)
    return _build_activation_result_from_snapshot(
        action_label=action_label,
        access_token=str(access_token or "").strip(),
        request_id=request_id,
        snapshot_data=status_data,
        accepted=True,
    )


def cancel_active_activation(
    expected_request_id: str = "",
    expected_action: str = "",
) -> Dict[str, Any]:
    """
    取消当前激活服务中的活动任务。

    参数:
        expected_request_id: 期望取消的 requestId，可为空
        expected_action: 期望取消的动作类型，可为空
    返回:
        Dict[str, Any]: 取消接口响应
        AI by zb
    """
    _validate_activation_config()

    status_data = get_service_status()
    active_request_id = str(status_data.get("activeRequestId") or "").strip()
    active_action = str(status_data.get("activeAction") or "").strip().lower()
    normalized_expected_request_id = str(expected_request_id or "").strip()
    normalized_expected_action = str(expected_action or "").strip().lower()

    if not active_request_id:
        raise RuntimeError("当前没有进行中的激活任务")

    if normalized_expected_request_id and normalized_expected_request_id != active_request_id:
        raise RuntimeError(
            f"当前活动任务 requestId 不匹配：active={active_request_id} expected={normalized_expected_request_id}"
        )

    if normalized_expected_action and active_action and normalized_expected_action not in active_action:
        raise RuntimeError(
            f"当前活动任务类型不匹配：active={active_action} expected={normalized_expected_action}"
        )

    payload = {"requestId": active_request_id}
    if active_action:
        payload["action"] = active_action

    result = _request_json("POST", "/api/v1/cancel", payload=payload)
    if not isinstance(result, dict):
        raise RuntimeError("取消接口返回数据格式异常")

    normalized_result = dict(result)
    normalized_result.setdefault("requestId", active_request_id)
    normalized_result.setdefault("activeAction", active_action)
    normalized_result.setdefault("message", "已提交取消请求")
    return normalized_result


def _request_activation(
    access_token: str,
    activation_path: str,
    action_label: str,
) -> tuple[Optional[Dict[str, Any]], bool]:
    """
    提交指定类型的激活请求。

    参数:
        access_token: ChatGPT accessToken
        activation_path: 激活接口路径
        action_label: 激活类型显示名称
    返回:
        tuple[Optional[Dict[str, Any]], bool]: (WorkflowResponse, 是否发生读超时)
        AI by zb
    """
    print(f"🚀 正在提交 {action_label} 激活请求...")
    session = _create_single_submit_session()
    url = f"{str(cfg.activation_api.base_url).rstrip('/')}{activation_path}"
    try:
        response = session.post(
            url=url,
            json={"accessToken": access_token},
            headers=_build_activation_headers(),
            timeout=ACTIVATION_SUBMIT_TIMEOUT_SECONDS,
        )
    except requests.exceptions.ReadTimeout:
        print(f"⏰ {action_label} 激活请求等待响应超时，接下来只轮询任务状态，不会再次提交")
        return None, True
    except Exception:
        raise

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(
            f"接口返回非 JSON: HTTP {response.status_code} | {response.text[:200]}"
        ) from exc

    if not response.ok:
        raise RuntimeError(
            f"接口调用失败: HTTP {response.status_code} | {data.get('message') or data.get('errorMessage') or response.text[:200]}"
        )

    if not isinstance(data, dict):
        raise RuntimeError("接口返回 JSON 不是对象结构")

    return data, False


def request_plus_activation(access_token: str) -> tuple[Optional[Dict[str, Any]], bool]:
    """
    提交 Plus 激活请求。

    参数:
        access_token: ChatGPT accessToken
    返回:
        tuple[Optional[Dict[str, Any]], bool]: (WorkflowResponse, 是否发生读超时)
        AI by zb
    """
    return _request_activation(access_token, "/api/v1/activate/plus", "Plus")


def request_team_activation(access_token: str) -> tuple[Optional[Dict[str, Any]], bool]:
    """
    提交 Team 激活请求。

    参数:
        access_token: ChatGPT accessToken
    返回:
        tuple[Optional[Dict[str, Any]], bool]: (WorkflowResponse, 是否发生读超时)
        AI by zb
    """
    return _request_activation(access_token, "/api/v1/activate/team", "Team")


def wait_for_active_request_id_after_timeout(
    timeout_seconds: int = ACTIVATION_TIMEOUT_STATUS_POLL_SECONDS,
    action_keywords: Optional[tuple[str, ...]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    action_label: str = "激活",
) -> Optional[str]:
    """
    提交超时后，轮询服务状态以获取当前激活任务 requestId。

    参数:
        timeout_seconds: 最大等待秒数
        action_keywords: 期望匹配的动作关键字
    返回:
        Optional[str]: requestId
        AI by zb
    """
    poll_interval = max(int(cfg.activation_api.poll_interval), 1)
    deadline = time.time() + max(int(timeout_seconds), 1)
    normalized_keywords = tuple(
        str(keyword or "").strip().lower()
        for keyword in (action_keywords or ())
        if str(keyword or "").strip()
    )

    while time.time() < deadline:
        _ensure_activation_not_cancelled(should_cancel, action_label)
        try:
            status_data = get_service_status()
        except Exception as exc:
            print(f"⚠️ 查询服务状态失败，继续重试: {exc}")
            time.sleep(poll_interval)
            continue

        active_request_id = str(status_data.get("activeRequestId") or "").strip()
        active_action = str(status_data.get("activeAction") or "").strip().lower()
        if active_request_id:
            if (
                not active_action
                or not normalized_keywords
                or any(keyword in active_action for keyword in normalized_keywords)
                or "activate" in active_action
            ):
                print(f"🔎 超时后已拿到活动任务 requestId: {active_request_id}")
                return active_request_id

        time.sleep(poll_interval)

    return None


def _activate_with_access_token(
    access_token: str,
    activation_path: str,
    action_label: str,
    cache_scope: str,
    action_keywords: tuple[str, ...],
    use_cache: bool = True,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PlusActivationResult:
    """
    直接使用已有 accessToken 调用指定激活接口。

    参数:
        access_token: ChatGPT accessToken
        activation_path: 激活接口路径
        action_label: 激活类型显示名称
        cache_scope: 缓存作用域
        action_keywords: 超时后轮询匹配关键字
        use_cache: 是否启用短时结果缓存
    返回:
        PlusActivationResult: 激活结果
        AI by zb
    """
    try:
        _validate_activation_config()
    except Exception as exc:
        return PlusActivationResult(success=False, stage="config", message=str(exc))

    normalized_token = str(access_token or "").strip()
    if not normalized_token:
        return PlusActivationResult(success=False, stage="fetch_token", message="缺少可用 accessToken")

    if use_cache:
        cached_result = _get_cached_plus_result(normalized_token, cache_scope=cache_scope)
        if cached_result:
            print(f"♻️ 检测到短时间内重复的 {action_label} 激活请求，直接复用上次结果")
            return cached_result

    request_id = ""
    try:
        _ensure_activation_not_cancelled(should_cancel, action_label)
        submit_data, timed_out = _request_activation(
            normalized_token,
            activation_path=activation_path,
            action_label=action_label,
        )
        submit_snapshot = dict(submit_data or {}) if isinstance(submit_data, dict) else {}

        if timed_out:
            request_id = str(
                wait_for_active_request_id_after_timeout(
                    timeout_seconds=ACTIVATION_TIMEOUT_STATUS_POLL_SECONDS,
                    action_keywords=action_keywords,
                    should_cancel=should_cancel,
                    action_label=action_label,
                )
                or ""
            ).strip()
            if not request_id:
                return PlusActivationResult(
                    success=False,
                    stage="activate",
                    access_token=normalized_token,
                    message=f"{action_label}激活请求已发送但响应超时，120秒内未获取到任务ID",
                )
            if not submit_snapshot:
                submit_snapshot = {
                    "requestId": request_id,
                    "status": "处理中",
                    "message": f"{action_label}激活请求已提交，请改用 requestId 轮询最终状态",
                }
        else:
            request_id = _extract_request_id(submit_snapshot)

        if not submit_snapshot and not request_id:
            raise RuntimeError("激活请求已提交，但未收到可用响应数据")

        if request_id and "requestId" not in submit_snapshot:
            submit_snapshot["requestId"] = request_id
        result = _build_submitted_activation_result(
            action_label=action_label,
            access_token=normalized_token,
            request_id=request_id,
            submit_data=submit_snapshot,
        )
        if _is_pending_activation_result(result):
            result = _poll_submitted_activation_result(
                action_label=action_label,
                access_token=normalized_token,
                result=result,
                action_keywords=action_keywords,
                should_cancel=should_cancel,
            )
        if use_cache and (result.success or result.accepted) and result.stage != "cancelled" and (request_id or submit_data is not None):
            _set_cached_plus_result(normalized_token, result, cache_scope=cache_scope)
        return result
    except ManualActivationCancelledError as exc:
        return PlusActivationResult(
            success=False,
            stage="cancelled",
            accepted=bool(request_id),
            access_token=normalized_token,
            request_id=request_id,
            message=str(exc),
        )
    except Exception as exc:
        return PlusActivationResult(
            success=False,
            stage="activate",
            access_token=normalized_token,
            message=str(exc),
        )


def activate_plus_with_access_token(
    access_token: str,
    use_cache: bool = True,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PlusActivationResult:
    """
    直接使用已有 accessToken 调用 Plus 激活接口。

    参数:
        access_token: ChatGPT accessToken
    返回:
        PlusActivationResult: 激活结果
        AI by zb
    """
    return _activate_with_access_token(
        access_token,
        activation_path="/api/v1/activate/plus",
        action_label="Plus",
        cache_scope="plus",
        action_keywords=("plus",),
        use_cache=use_cache,
        should_cancel=should_cancel,
    )


def activate_team_with_access_token(
    access_token: str,
    use_cache: bool = True,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PlusActivationResult:
    """
    直接使用已有 accessToken 调用 Team 激活接口。

    参数:
        access_token: ChatGPT accessToken
    返回:
        PlusActivationResult: 激活结果
        AI by zb
    """
    return _activate_with_access_token(
        access_token,
        activation_path="/api/v1/activate/team",
        action_label="Team",
        cache_scope="team",
        action_keywords=("team",),
        use_cache=use_cache,
        should_cancel=should_cancel,
    )


def poll_request_status(
    request_id: str,
    timeout_seconds: Optional[int] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    action_label: str = "激活",
) -> Dict[str, Any]:
    """
    轮询异步任务状态直到结束。

    参数:
        request_id: 任务请求 ID
        timeout_seconds: 最大轮询秒数
    返回:
        Dict[str, Any]: RequestStatusResponse
        AI by zb
    """
    effective_timeout_seconds = (
        max(int(timeout_seconds), 1)
        if timeout_seconds is not None
        else max(int(cfg.activation_api.poll_timeout), 1)
    )
    poll_interval = max(int(cfg.activation_api.poll_interval), 1)
    deadline = time.time() + effective_timeout_seconds
    poll_failure_count = 0
    last_poll_error = ""

    while time.time() < deadline:
        _ensure_activation_not_cancelled(should_cancel, action_label)
        try:
            status_data = get_request_status(request_id)
        except Exception as exc:
            poll_failure_count += 1
            last_poll_error = str(exc or "").strip()
            print(
                f"⚠️ 激活任务轮询失败，第 {poll_failure_count} 次沿用原 requestId 继续查询: "
                f"requestId={request_id} | {last_poll_error or exc}"
            )
            time.sleep(poll_interval)
            continue

        poll_failure_count = 0
        state = str(status_data.get("state") or "").strip().lower()
        print(
            f"⏳ 激活任务轮询中: requestId={request_id} "
            f"{_summarize_activation_snapshot(status_data)}"
        )

        if state in {"completed", "failed", "cancelled"}:
            return status_data

        time.sleep(poll_interval)

    timeout_message = f"任务轮询超时: requestId={request_id}"
    if last_poll_error:
        timeout_message = f"{timeout_message} | 最近一次轮询错误: {last_poll_error}"
    raise TimeoutError(timeout_message)


def _poll_submitted_activation_result(
    action_label: str,
    access_token: str,
    result: PlusActivationResult,
    action_keywords: tuple[str, ...],
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PlusActivationResult:
    """
    对已提交的激活任务执行阻塞轮询，直到进入终态。

    参数:
        action_label: 激活类型显示名称
        access_token: ChatGPT accessToken
        result: 激活提交结果
        action_keywords: 活动任务匹配关键字
        should_cancel: 取消检查函数
    返回:
        PlusActivationResult: 终态结果
        AI by zb
    """
    request_id = str(result.request_id or "").strip()
    if not request_id:
        request_id = str(
            wait_for_active_request_id_after_timeout(
                timeout_seconds=ACTIVATION_TIMEOUT_STATUS_POLL_SECONDS,
                action_keywords=action_keywords,
                should_cancel=should_cancel,
                action_label=action_label,
            )
            or ""
        ).strip()
        if not request_id:
            return PlusActivationResult(
                success=False,
                stage="activate",
                accepted=False,
                access_token=access_token,
                message=f"{action_label}激活请求已提交，但未获取到可轮询的 requestId",
                response_data=dict(result.response_data or {}),
            )

    print(f"🔄 {action_label} 激活已提交，开始阻塞轮询最终结果: requestId={request_id}")
    final_snapshot = poll_request_status(
        request_id=request_id,
        should_cancel=should_cancel,
        action_label=action_label,
    )
    final_result = _build_activation_result_from_snapshot(
        action_label=action_label,
        access_token=access_token,
        request_id=request_id,
        snapshot_data=final_snapshot,
        accepted=True,
    )
    snapshot_summary = _summarize_activation_snapshot(final_snapshot)

    if final_result.success:
        print(f"✅ {action_label} 激活轮询完成: requestId={request_id} {snapshot_summary}")
    elif str(final_result.stage or "").strip().lower() == "cancelled":
        print(f"🛑 {action_label} 激活任务已取消: requestId={request_id} {snapshot_summary}")
    else:
        print(
            f"❌ {action_label} 激活轮询结束但未成功: requestId={request_id} | "
            f"{snapshot_summary} | {final_result.message or final_result.status or final_result.stage}"
        )
    return final_result


def _activate_with_browser_session(
    driver,
    action_label: str,
    activation_handler,
    use_cache: bool = True,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PlusActivationResult:
    """
    完整执行“提取 accessToken + 调用激活接口 + 轮询结果”流程。

    参数:
        driver: Selenium WebDriver
        action_label: 激活类型显示名称
        activation_handler: 基于 accessToken 的激活函数
        use_cache: 是否启用短时结果缓存
    返回:
        PlusActivationResult: 流程结果
        AI by zb
    """
    try:
        _validate_activation_config()
    except Exception as exc:
        return PlusActivationResult(
            success=False,
            stage="config",
            message=str(exc),
        )

    try:
        print("⏳ 等待页面稳定后再提取 accessToken...")
        _wait_for_page_stable_before_fetch(driver)
        access_token = fetch_access_token(driver)
        print("⏳ accessToken 提取完成，等待 1 秒后再提取 session 信息...")
        time.sleep(1)
        session_info = fetch_session_info(driver)
    except Exception as exc:
        return PlusActivationResult(
            success=False,
            stage="fetch_token",
            message=str(exc),
        )
    result = activation_handler(
        access_token,
        use_cache=use_cache,
        should_cancel=should_cancel,
    )
    result.session_info = session_info
    if isinstance(result.response_data, dict):
        result.response_data["sessionInfo"] = session_info
        result.response_data["activationType"] = action_label.lower()
    return result


def activate_plus_with_browser_session(
    driver,
    use_cache: bool = True,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PlusActivationResult:
    """
    完整执行“提取 accessToken + 调用 Plus 激活接口 + 轮询结果”流程。

    参数:
        driver: Selenium WebDriver
    返回:
        PlusActivationResult: 流程结果
        AI by zb
    """
    return _activate_with_browser_session(
        driver,
        "Plus",
        activate_plus_with_access_token,
        use_cache=use_cache,
        should_cancel=should_cancel,
    )


def activate_team_with_browser_session(
    driver,
    use_cache: bool = True,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PlusActivationResult:
    """
    完整执行“提取 accessToken + 调用 Team 激活接口 + 轮询结果”流程。

    参数:
        driver: Selenium WebDriver
    返回:
        PlusActivationResult: 流程结果
        AI by zb
    """
    return _activate_with_browser_session(
        driver,
        "Team",
        activate_team_with_access_token,
        use_cache=use_cache,
        should_cancel=should_cancel,
    )
