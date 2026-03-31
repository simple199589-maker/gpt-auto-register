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
from app.plus_activation_api import PlusActivationResult
from app.plus_binding import (
    is_access_token_plus_binding_mode,
    run_plus_binding_with_access_token,
    run_plus_binding_with_browser_session,
)
from app.utils import get_account_record, upsert_account_record


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

    updates = {
        "status": overall_status,
        "accessToken": access_token or result.access_token or "",
        "plusCalled": True,
        "plusSuccess": bool(result.success),
        "plusStatus": result.status or overall_status,
        "plusMessage": result.message,
        "plusRequestId": result.request_id,
        "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
        "sessionInfo": (result.response_data or {}).get("sessionInfo") or {},
    }
    return upsert_account_record(email, updates)


def run_plus_retry_for_account(email: str, monitor_callback=None) -> PlusActivationResult:
    """
    对指定账号执行 Plus 重试。

    会根据当前 `plus.mode` 自动选择重试方式。

    参数:
        email: 邮箱地址
        monitor_callback: 浏览器监控回调
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

    if stored_access_token and supports_access_token:
        print(f"🚀 复用已保存 accessToken 重试 Plus: {email}")
        result = run_plus_binding_with_access_token(stored_access_token)
        _save_plus_result(email, result, access_token=stored_access_token)
        if result.success or not password or password == "N/A":
            return result
        print(f"⚠️ 已保存 accessToken 重试失败，尝试浏览器重新登录刷新 token: {email}")
    elif stored_access_token:
        print(f"ℹ️ 当前 Plus 模式不支持仅凭 accessToken 重试，将改为浏览器登录模式: {email}")

    if not password or password == "N/A":
        return PlusActivationResult(success=False, stage="login", message="账号未保存可用密码，无法重新登录提取 token")

    driver = None
    try:
        print(f"🌐 尝试浏览器登录后执行当前配置的 Plus 绑定流程: {email}")
        driver = create_driver(headless=not cfg.browser.show_browser_window)
        if monitor_callback:
            monitor_callback(driver, "driver_ready")
        if not login(driver, email, password):
            return PlusActivationResult(success=False, stage="login", message="浏览器登录失败")
        result = run_plus_binding_with_browser_session(driver)
        _save_plus_result(email, result)
        return result
    except Exception as exc:
        return PlusActivationResult(success=False, stage="login", message=str(exc))
    finally:
        if driver:
            if monitor_callback:
                try:
                    monitor_callback(driver, "driver_closing")
                except Exception:
                    pass
            try:
                driver.quit()
            except Exception:
                pass


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
                "sub2apiUploaded": bool(uploaded),
                "sub2apiStatus": "已上传" if uploaded else "上传失败",
                "sub2apiMessage": result.message,
                "sub2apiUploadedAt": time.strftime("%Y%m%d_%H%M%S") if uploaded else "",
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
                "sub2apiUploaded": False,
                "sub2apiStatus": "获取上传Token失败",
                "sub2apiMessage": result.message,
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
            "sub2apiUploaded": bool(uploaded),
            "sub2apiStatus": "已上传" if uploaded else "上传失败",
            "sub2apiMessage": result.message,
            "sub2apiUploadedAt": time.strftime("%Y%m%d_%H%M%S") if uploaded else "",
            "oauthTokens": tokens,
            "oauthOutputFile": output_file,
        },
    )
    return result
