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
from typing import Any, Dict, Optional

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
    access_token: str = ""
    request_id: str = ""
    status: str = ""
    message: str = ""
    response_data: Dict[str, Any] = field(default_factory=dict)
    session_info: Dict[str, Any] = field(default_factory=dict)


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

    try:
        submit_data, timed_out = _request_activation(
            normalized_token,
            activation_path=activation_path,
            action_label=action_label,
        )
        request_id = ""
        final_data: Optional[Dict[str, Any]] = submit_data

        if timed_out:
            request_id = str(
                wait_for_active_request_id_after_timeout(
                    timeout_seconds=ACTIVATION_TIMEOUT_STATUS_POLL_SECONDS,
                    action_keywords=action_keywords,
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
            final_data = poll_request_status(
                request_id,
                timeout_seconds=ACTIVATION_TIMEOUT_STATUS_POLL_SECONDS,
            )
        else:
            request_id = str((submit_data or {}).get("requestId") or "").strip()
            if request_id:
                final_data = poll_request_status(request_id)

        if not isinstance(final_data, dict):
            raise RuntimeError("未获取到有效的激活结果")

        success = bool(final_data.get("success"))
        final_state = str(final_data.get("state") or final_data.get("status") or "").strip().lower()
        is_cancelled = final_state in {"cancelled", "canceled"}
        result_message = str(final_data.get("message") or final_data.get("rawMessage") or "").strip()
        if is_cancelled and not result_message:
            result_message = f"{action_label}激活已取消"
        result = PlusActivationResult(
            success=success,
            stage="completed" if success else ("cancelled" if is_cancelled else "activate"),
            access_token=normalized_token,
            request_id=request_id,
            status=str(final_data.get("status") or final_data.get("state") or "").strip(),
            message=result_message,
            response_data=final_data,
        )
        if use_cache and not is_cancelled and (request_id or submit_data is not None):
            _set_cached_plus_result(normalized_token, result, cache_scope=cache_scope)
        return result
    except Exception as exc:
        return PlusActivationResult(
            success=False,
            stage="activate",
            access_token=normalized_token,
            message=str(exc),
        )


def activate_plus_with_access_token(access_token: str, use_cache: bool = True) -> PlusActivationResult:
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
    )


def activate_team_with_access_token(access_token: str, use_cache: bool = True) -> PlusActivationResult:
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
    )


def poll_request_status(
    request_id: str,
    timeout_seconds: Optional[int] = None,
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

    while time.time() < deadline:
        status_data = _request_json("GET", f"/api/v1/requests/{request_id}")
        state = str(status_data.get("state") or "").strip().lower()
        print(f"⏳ 激活任务轮询中: requestId={request_id} state={state or 'unknown'}")

        if state in {"completed", "failed", "cancelled"}:
            return status_data

        time.sleep(poll_interval)

    raise TimeoutError(f"任务轮询超时: requestId={request_id}")


def _activate_with_browser_session(
    driver,
    action_label: str,
    activation_handler,
    use_cache: bool = True,
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
    result = activation_handler(access_token, use_cache=use_cache)
    result.session_info = session_info
    if isinstance(result.response_data, dict):
        result.response_data["sessionInfo"] = session_info
        result.response_data["activationType"] = action_label.lower()
    return result


def activate_plus_with_browser_session(driver, use_cache: bool = True) -> PlusActivationResult:
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
    )


def activate_team_with_browser_session(driver, use_cache: bool = True) -> PlusActivationResult:
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
    )
