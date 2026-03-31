"""
账号动作编排。
AI by zb
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.browser import create_driver, login
from app.codex.runtime import (
    build_token_dict,
    get_logger,
    load_runtime_config,
    perform_http_oauth_login,
    resolve_proxy,
    save_token_payload,
    upload_to_sub2api,
)
from app.config import cfg
from app.plus_activation_api import (
    PlusActivationResult,
    activate_team_with_access_token,
    activate_team_with_browser_session,
    cancel_active_activation,
)
from app.plus_binding import (
    is_access_token_plus_binding_mode,
    run_plus_binding_with_access_token,
    run_plus_binding_with_browser_session,
)
from app.utils import delete_account_record, get_account_record, upsert_account_record


@dataclass
class Sub2ApiUploadResult:
    """
    Sub2Api 上传编排结果。

    AI by zb
    """

    success: bool
    uploaded: bool = False
    stage: str = ""
    message: str = ""
    output_file: str = ""
    tokens: Dict[str, Any] = field(default_factory=dict)
    token_payload: Dict[str, Any] = field(default_factory=dict)


def is_plus_auto_activation_enabled() -> bool:
    """
    判断是否启用自动 Plus 激活。

    返回:
        bool: 是否启用
        AI by zb
    """
    return bool(cfg.plus.auto_activate)


def is_sub2api_auto_upload_enabled() -> bool:
    """
    判断是否启用自动上传 Sub2Api。

    返回:
        bool: 是否启用
        AI by zb
    """
    return bool(cfg.sub2api.auto_upload_sub2api and str(cfg.sub2api.base_url or "").strip())


def has_complete_oauth_tokens(account: dict) -> bool:
    """
    判断账号记录中是否已保存完整 OAuth 三件套。

    参数:
        account: 账号记录
    返回:
        bool: 是否完整
        AI by zb
    """
    oauth_tokens = (account or {}).get("oauthTokens") or {}
    return bool(
        str(oauth_tokens.get("access_token") or "").strip()
        and str(oauth_tokens.get("refresh_token") or "").strip()
        and str(oauth_tokens.get("id_token") or "").strip()
    )


def _save_plus_result(email: str, result: PlusActivationResult, access_token: str = "") -> dict:
    """
    将 Plus 激活结果写回账号记录。

    参数:
        email: 邮箱地址
        result: Plus 激活结果
        access_token: 可选的 accessToken
    返回:
        dict: 更新后的账号记录
        AI by zb
    """
    overall_status = "已激活Plus" if result.success else "Plus绑定失败"
    if result.stage == "fetch_token":
        overall_status = "Token获取失败"
    if result.stage == "config":
        overall_status = "Plus配置缺失"
    if result.stage == "cancelled":
        overall_status = "Plus已取消"

    updates = {
        "status": overall_status,
        "registrationStatus": "success",
        "overallStatus": "success" if result.success else "failed",
        "accessToken": access_token or result.access_token or "",
        "plusCalled": True,
        "plusSuccess": bool(result.success),
        "plusState": "success" if result.success else "failed",
        "plusStatus": result.status or overall_status,
        "plusMessage": result.message,
        "plusRequestId": result.request_id,
        "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
        "sessionInfo": (result.response_data or {}).get("sessionInfo") or {},
        "lastError": "" if result.success or result.stage == "cancelled" else (result.message or overall_status),
    }
    return upsert_account_record(email, updates)


def _get_manual_activation_attempts() -> int:
    """
    获取手动激活最大重试轮数。

    返回:
        int: 最大重试轮数
        AI by zb
    """
    return max(int(getattr(cfg.retry, "manual_activation_attempts", 3) or 1), 1)


def _mark_activation_pending(email: str, status_text: str) -> None:
    """
    将指定账号标记为激活进行中。

    参数:
        email: 邮箱地址
        status_text: 展示状态文本
    返回:
        None
        AI by zb
    """
    upsert_account_record(
        email,
        {
            "status": status_text,
            "registrationStatus": "success",
            "overallStatus": "pending",
            "plusCalled": True,
            "plusSuccess": False,
            "plusState": "pending",
            "plusStatus": status_text,
            "plusMessage": "",
            "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
            "lastError": "",
        },
    )


def _should_stop_manual_activation_retry(result: PlusActivationResult) -> bool:
    """
    判断手动激活失败后是否应立即停止后续重试。

    参数:
        result: 当前尝试结果
    返回:
        bool: 是否停止
        AI by zb
    """
    if result.success:
        return True
    if result.stage in {"account", "config", "mode"}:
        return True
    if result.stage == "login" and "未保存可用密码" in str(result.message or ""):
        return True
    return False


def _decorate_manual_activation_result(
    action_label: str,
    result: PlusActivationResult,
    attempt_index: int,
    max_attempts: int,
) -> PlusActivationResult:
    """
    为手动激活结果补充重试轮次信息，便于前端提示。

    参数:
        action_label: 激活类型名称
        result: 原始结果
        attempt_index: 实际执行次数
        max_attempts: 最大重试轮数
    返回:
        PlusActivationResult: 补充后的结果
        AI by zb
    """
    if max_attempts <= 1:
        return result

    base_message = str(result.message or "").strip()
    if result.success:
        prefix = f"{action_label} 第 {attempt_index}/{max_attempts} 次尝试成功"
        result.message = f"{prefix}：{base_message}" if base_message else prefix
        return result

    if attempt_index >= max_attempts:
        prefix = f"{action_label} 已达到最大重试次数({max_attempts})"
        result.message = f"{prefix}：{base_message}" if base_message else prefix
    return result


def _run_manual_activation_with_retries(
    action_label: str,
    email: str,
    attempt_runner,
) -> PlusActivationResult:
    """
    按配置的轮数执行手动激活重试。

    参数:
        action_label: 激活类型名称
        email: 邮箱地址
        attempt_runner: 单次尝试执行器
    返回:
        PlusActivationResult: 最终结果
        AI by zb
    """
    max_attempts = _get_manual_activation_attempts()
    final_result = PlusActivationResult(success=False, stage="activate", message=f"{action_label}未开始执行")
    actual_attempts = 0

    for attempt_index in range(1, max_attempts + 1):
        actual_attempts = attempt_index
        print(f"🔁 {action_label} 第 {attempt_index}/{max_attempts} 次尝试: {email}")
        final_result = attempt_runner()
        if final_result.success:
            break
        if _should_stop_manual_activation_retry(final_result):
            break
        if attempt_index < max_attempts:
            print(f"⚠️ {action_label} 第 {attempt_index}/{max_attempts} 次失败，准备继续重试: {final_result.message or final_result.status or final_result.stage}")

    return _decorate_manual_activation_result(
        action_label,
        final_result,
        actual_attempts,
        max_attempts,
    )


def _classify_manual_status_text(status_text: str) -> str:
    """
    根据手动输入的状态文案推断状态分类。

    参数:
        status_text: 手动输入的状态文本
    返回:
        str: `pending/success/failed`
        AI by zb
    """
    text = str(status_text or "").strip()
    if not text:
        return "pending"
    if text == "注册中" or "处理中" in text:
        return "pending"
    if any(keyword in text for keyword in ("失败", "错误", "异常", "中断", "缺失")):
        return "failed"
    return "success"


def run_manual_status_update_for_account(email: str, status_text: str) -> dict:
    """
    手动修改指定账号的主状态。

    参数:
        email: 邮箱地址
        status_text: 新状态文本
    返回:
        dict: 更新后的账号记录
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        raise ValueError("账号不存在")

    normalized_status = str(status_text or "").strip()
    if not normalized_status:
        raise ValueError("状态不能为空")

    inferred_state = _classify_manual_status_text(normalized_status)
    return upsert_account_record(
        email,
        {
            "status": normalized_status,
            "registrationStatus": inferred_state,
            "overallStatus": inferred_state,
            "plusCalled": False,
            "plusSuccess": False,
            "plusState": "idle",
            "plusStatus": "",
            "plusMessage": "",
            "plusRequestId": "",
            "plusCalledAt": "",
            "lastError": "",
        },
    )


def run_delete_account_for_email(email: str) -> bool:
    """
    删除指定账号记录。

    参数:
        email: 邮箱地址
    返回:
        bool: 是否删除成功
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        return False
    return bool(delete_account_record(email))


def run_plus_retry_for_account(email: str) -> PlusActivationResult:
    """
    对指定账号执行 Plus 重试。

    会根据当前 `plus.mode` 自动选择重试方式。

    参数:
        email: 邮箱地址
    返回:
        PlusActivationResult: 激活结果
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        return PlusActivationResult(success=False, stage="account", message="账号不存在")

    stored_access_token = str(account.get("accessToken") or "").strip()
    password = str(account.get("password") or "").strip()
    supports_access_token = is_access_token_plus_binding_mode()
    _mark_activation_pending(email, "Plus激活中")

    if stored_access_token and supports_access_token:
        result = _run_manual_activation_with_retries(
            "Plus激活",
            email,
            lambda: run_plus_binding_with_access_token(stored_access_token, use_cache=False),
        )
        _save_plus_result(email, result, access_token=stored_access_token)
        return result
    elif stored_access_token:
        print(f"ℹ️ 当前 Plus 模式不支持仅凭 accessToken 重试，将改为浏览器登录模式: {email}")

    if not password or password == "N/A":
        return PlusActivationResult(success=False, stage="login", message="账号未保存可用密码，无法重新登录提取 token")

    driver = None
    def attempt_runner() -> PlusActivationResult:
        nonlocal driver
        driver = None
        try:
            print(f"🌐 尝试浏览器登录后执行当前配置的 Plus 绑定流程: {email}")
            driver = create_driver(headless=not cfg.browser.show_browser_window)
            if not login(driver, email, password):
                return PlusActivationResult(success=False, stage="login", message="浏览器登录失败")
            return run_plus_binding_with_browser_session(driver, use_cache=False)
        except Exception as exc:
            return PlusActivationResult(success=False, stage="login", message=str(exc))
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None

    result = _run_manual_activation_with_retries("Plus激活", email, attempt_runner)
    _save_plus_result(email, result)
    return result


def run_team_retry_for_account(email: str) -> PlusActivationResult:
    """
    对指定账号执行 Team 激活重试。

    参数:
        email: 邮箱地址
    返回:
        PlusActivationResult: 激活结果
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        return PlusActivationResult(success=False, stage="account", message="账号不存在")

    stored_access_token = str(account.get("accessToken") or "").strip()
    password = str(account.get("password") or "").strip()
    _mark_activation_pending(email, "Team激活中")

    if stored_access_token:
        return _run_manual_activation_with_retries(
            "Team激活",
            email,
            lambda: activate_team_with_access_token(stored_access_token, use_cache=False),
        )

    if not password or password == "N/A":
        return PlusActivationResult(success=False, stage="login", message="账号未保存可用密码，无法重新登录提取 token")

    driver = None
    def attempt_runner() -> PlusActivationResult:
        nonlocal driver
        driver = None
        try:
            print(f"🌐 尝试浏览器登录后执行 Team 激活流程: {email}")
            driver = create_driver(headless=not cfg.browser.show_browser_window)
            if not login(driver, email, password):
                return PlusActivationResult(success=False, stage="login", message="浏览器登录失败")
            return activate_team_with_browser_session(driver, use_cache=False)
        except Exception as exc:
            return PlusActivationResult(success=False, stage="login", message=str(exc))
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None

    return _run_manual_activation_with_retries("Team激活", email, attempt_runner)


def run_cancel_activation_for_account(email: str) -> Dict[str, Any]:
    """
    取消指定账号当前对应的激活任务。

    参数:
        email: 邮箱地址
    返回:
        Dict[str, Any]: 取消结果
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        raise ValueError("账号不存在")

    result = cancel_active_activation()
    request_id = str(result.get("requestId") or "").strip()
    upsert_account_record(
        email,
        {
            "status": "取消中",
            "overallStatus": "pending",
            "plusCalled": True,
            "plusSuccess": False,
            "plusState": "pending",
            "plusStatus": "取消中",
            "plusMessage": str(result.get("message") or "已提交取消请求").strip(),
            "plusRequestId": request_id,
            "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
        },
    )
    return result


def run_sub2api_upload_for_account(email: str) -> Sub2ApiUploadResult:
    """
    对指定账号执行 Sub2Api 上传。

    优先复用已保存 OAuth 三件套；若缺失则使用原有 Codex OAuth 逻辑重新获取后上传。

    参数:
        email: 邮箱地址
    返回:
        Sub2ApiUploadResult: 上传结果
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        return Sub2ApiUploadResult(success=False, stage="account", message="账号不存在")

    config = load_runtime_config("")
    logger = get_logger("account-sub2api")
    oauth_tokens = (account.get("oauthTokens") or {}) if isinstance(account, dict) else {}

    if has_complete_oauth_tokens(account):
        print(f"📤 复用已保存 OAuth 三件套上传 Sub2Api: {email}")
        uploaded = upload_to_sub2api(email, oauth_tokens, config, logger=logger)
        result = Sub2ApiUploadResult(
            success=uploaded,
            uploaded=uploaded,
            stage="upload",
            message="上传成功" if uploaded else "上传失败",
            tokens=oauth_tokens,
            token_payload=build_token_dict(email, oauth_tokens),
        )
        upsert_account_record(
            email,
            {
                "status": "已上传Sub2Api" if uploaded else "Sub2Api上传失败",
                "overallStatus": "success" if uploaded else "failed",
                "sub2apiUploaded": bool(uploaded),
                "sub2apiState": "success" if uploaded else "failed",
                "sub2apiStatus": "已上传" if uploaded else "上传失败",
                "sub2apiMessage": result.message,
                "sub2apiUploadedAt": time.strftime("%Y%m%d_%H%M%S") if uploaded else "",
                "lastError": "" if uploaded else result.message,
            },
        )
        return result

    password = str(account.get("password") or "").strip()
    if not password or password == "N/A":
        return Sub2ApiUploadResult(success=False, stage="token", message="账号未保存可用密码，无法获取 OAuth 三件套")

    mailbox_context = str(account.get("mailboxContext") or "").strip()
    print(f"🔐 开始走原始 Codex OAuth 逻辑获取三件套: {email}")
    effective_proxy = resolve_proxy(config, "")
    tokens = perform_http_oauth_login(
        email=email,
        password=password,
        proxy=effective_proxy,
        otp_mode="auto",
        mailbox_context=mailbox_context,
        logger=logger,
    )
    if not tokens:
        result = Sub2ApiUploadResult(success=False, stage="token", message="未获取到 OAuth 三件套")
        upsert_account_record(
            email,
            {
                "status": "Sub2Api上传失败",
                "overallStatus": "failed",
                "sub2apiUploaded": False,
                "sub2apiState": "failed",
                "sub2apiStatus": "获取上传Token失败",
                "sub2apiMessage": result.message,
                "lastError": result.message,
            },
        )
        return result

    token_payload = build_token_dict(email, tokens)
    output_file = save_token_payload(email, token_payload, output_dir="")
    print(f"💾 OAuth token 已保存: {output_file}")

    uploaded = upload_to_sub2api(email, tokens, config, logger=logger)
    result = Sub2ApiUploadResult(
        success=uploaded,
        uploaded=uploaded,
        stage="upload",
        message="上传成功" if uploaded else "上传失败",
        output_file=output_file,
        tokens=tokens,
        token_payload=token_payload,
    )
    upsert_account_record(
        email,
        {
            "status": "已上传Sub2Api" if uploaded else "Sub2Api上传失败",
            "overallStatus": "success" if uploaded else "failed",
            "sub2apiUploaded": bool(uploaded),
            "sub2apiState": "success" if uploaded else "failed",
            "sub2apiStatus": "已上传" if uploaded else "上传失败",
            "sub2apiMessage": result.message,
            "sub2apiUploadedAt": time.strftime("%Y%m%d_%H%M%S") if uploaded else "",
            "oauthTokens": tokens,
            "oauthOutputFile": output_file,
            "lastError": "" if uploaded else result.message,
        },
    )
    return result
