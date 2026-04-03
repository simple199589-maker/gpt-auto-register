"""
账号动作编排。
AI by zb
"""

from __future__ import annotations

import random
import re
import threading
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
from app.email_service import create_temp_access_url, send_single_email
from app.plus_activation_api import (
    PlusActivationResult,
    activate_team_with_access_token,
    activate_team_with_browser_session,
    cancel_active_activation,
    query_activation_request_result,
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


@dataclass
class AccountDeliveryResult:
    """
    账号发货编排结果。

    AI by zb
    """

    success: bool
    delivered: bool = False
    stage: str = ""
    message: str = ""
    vendor: str = ""
    delivery_email: str = ""
    temp_access_url: str = ""
    temp_access_ready: bool = False
    mail_id: str = ""


_MANUAL_ACTIVATION_CANCEL_LOCK = threading.Lock()
_MANUAL_ACTIVATION_CANCEL_REQUESTS: set[str] = set()


def _normalize_activation_email(email: str) -> str:
    """
    规范化手动激活相关邮箱标识，便于跨线程共享取消状态。

    参数:
        email: 原始邮箱
    返回:
        str: 规范化后的邮箱
        AI by zb
    """
    return str(email or "").strip().lower()


def request_manual_activation_cancel(email: str) -> None:
    """
    标记指定账号已请求停止后续手动激活重试。

    参数:
        email: 邮箱地址
    返回:
        None
        AI by zb
    """
    normalized_email = _normalize_activation_email(email)
    if not normalized_email:
        return
    with _MANUAL_ACTIVATION_CANCEL_LOCK:
        _MANUAL_ACTIVATION_CANCEL_REQUESTS.add(normalized_email)


def clear_manual_activation_cancel_request(email: str) -> None:
    """
    清除指定账号的手动激活取消标记。

    参数:
        email: 邮箱地址
    返回:
        None
        AI by zb
    """
    normalized_email = _normalize_activation_email(email)
    if not normalized_email:
        return
    with _MANUAL_ACTIVATION_CANCEL_LOCK:
        _MANUAL_ACTIVATION_CANCEL_REQUESTS.discard(normalized_email)


def is_manual_activation_cancel_requested(email: str) -> bool:
    """
    判断指定账号是否已请求停止后续手动激活重试。

    参数:
        email: 邮箱地址
    返回:
        bool: 是否已请求取消
        AI by zb
    """
    normalized_email = _normalize_activation_email(email)
    if not normalized_email:
        return False
    with _MANUAL_ACTIVATION_CANCEL_LOCK:
        return normalized_email in _MANUAL_ACTIVATION_CANCEL_REQUESTS


def _build_manual_activation_cancelled_result(action_label: str) -> PlusActivationResult:
    """
    构造统一的手动激活取消结果。

    参数:
        action_label: 激活类型名称
    返回:
        PlusActivationResult: 取消结果
        AI by zb
    """
    return PlusActivationResult(success=False, stage="cancelled", message=f"{action_label}已取消")


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


def _is_activation_request_accepted(result: PlusActivationResult) -> bool:
    """
    判断激活请求是否已经成功提交到远端服务。

    参数:
        result: 激活结果
    返回:
        bool: 是否已提交成功
        AI by zb
    """
    return bool(result.success or result.accepted)


def _save_plus_result(
    email: str,
    result: PlusActivationResult,
    access_token: str = "",
    action_label: str = "Plus",
) -> dict:
    """
    将 Plus 激活结果写回账号记录。

    参数:
        email: 邮箱地址
        result: Plus 激活结果
        access_token: 可选的 accessToken
        action_label: 激活类型名称
    返回:
        dict: 更新后的账号记录
        AI by zb
    """
    is_submitted = str(result.stage or "").strip().lower() == "submitted"
    success_status = "已激活Plus" if action_label == "Plus" else f"{action_label}激活成功"
    failure_status = "Plus绑定失败" if action_label == "Plus" else f"{action_label}激活失败"
    submitted_status = f"{action_label}激活已提交"
    cancelled_status = f"{action_label}已取消"
    config_status = "Plus配置缺失" if action_label == "Plus" else f"{action_label}配置缺失"

    overall_status = success_status if result.success else failure_status
    if result.stage == "fetch_token":
        overall_status = "Token获取失败"
    if result.stage == "config":
        overall_status = config_status
    if result.stage == "cancelled":
        overall_status = cancelled_status
    if is_submitted:
        overall_status = submitted_status

    overall_state = "success" if result.success else ("pending" if is_submitted else "failed")
    plus_state = "success" if result.success else ("pending" if is_submitted else "failed")

    updates = {
        "status": overall_status,
        "registrationStatus": "success",
        "overallStatus": overall_state,
        "accessToken": access_token or result.access_token or "",
        "plusCalled": True,
        "plusSuccess": bool(result.success),
        "plusState": plus_state,
        "plusStatus": result.status or ("处理中" if is_submitted else overall_status),
        "plusMessage": result.message,
        "plusRequestId": result.request_id,
        "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
        "sessionInfo": (result.response_data or {}).get("sessionInfo") or {},
        "lastError": "" if result.success or is_submitted or result.stage == "cancelled" else (result.message or overall_status),
    }
    return upsert_account_record(email, updates)


def _get_manual_activation_attempts() -> int:
    """
    获取手动激活最大重试轮数。

    返回:
        int: 最大重试轮数
        AI by zb
    """
    configured_attempts = max(int(getattr(cfg.retry, "manual_activation_attempts", 3) or 1), 1)
    return min(configured_attempts, 10)


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
    stage = str(result.stage or "").strip().lower()
    if result.success:
        return True
    if stage == "submitted":
        return True
    if stage == "cancelled":
        return True
    if stage in {"account", "config", "mode"}:
        return True
    if stage == "login" and "未保存可用密码" in str(result.message or ""):
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
    if str(result.stage or "").strip().lower() == "submitted":
        prefix = f"{action_label} 第 {attempt_index}/{max_attempts} 次尝试已提交"
        result.message = f"{prefix}：{base_message}" if base_message else prefix
        return result

    if attempt_index >= max_attempts:
        prefix = f"{action_label} 已达到最大重试次数({max_attempts})"
        result.message = f"{prefix}：{base_message}" if base_message else prefix
    return result


def _wait_before_next_manual_activation_attempt(
    action_label: str,
    email: str,
    next_attempt_index: int,
    max_attempts: int,
) -> bool:
    """
    在下一轮手动激活重试前执行短暂随机等待。

    参数:
        action_label: 激活类型名称
        email: 邮箱地址
        next_attempt_index: 下一轮尝试序号
        max_attempts: 最大重试轮数
    返回:
        bool: 等待期间是否收到取消请求
        AI by zb
    """
    wait_seconds = random.randint(2, 5)
    print(f"⏳ {action_label} 将随机等待 {wait_seconds} 秒后进入第 {next_attempt_index}/{max_attempts} 轮")
    for remaining_seconds in range(wait_seconds, 0, -1):
        if is_manual_activation_cancel_requested(email):
            print(f"🛑 {action_label} 在下一轮开始前收到取消请求，停止后续重试")
            return True
        print(f"⏱️ {action_label} 下一轮倒计时: {remaining_seconds} 秒")
        time.sleep(1)
    return False


def _infer_activation_action_label(account: Optional[dict]) -> str:
    """
    根据账号记录推断当前激活类型标签。

    参数:
        account: 账号记录
    返回:
        str: `Plus` 或 `Team`
        AI by zb
    """
    if not isinstance(account, dict):
        return "Plus"

    combined_text = " ".join(
        [
            str(account.get("plusStatus") or ""),
            str(account.get("status") or ""),
            str(account.get("plusMessage") or ""),
        ]
    ).strip().lower()
    return "Team" if "team" in combined_text else "Plus"


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
    normalized_email = _normalize_activation_email(email)
    clear_manual_activation_cancel_request(normalized_email)

    try:
        for attempt_index in range(1, max_attempts + 1):
            if is_manual_activation_cancel_requested(normalized_email):
                final_result = _build_manual_activation_cancelled_result(action_label)
                actual_attempts = max(actual_attempts, attempt_index - 1)
                break

            actual_attempts = attempt_index
            print(f"🔁 {action_label} 第 {attempt_index}/{max_attempts} 次尝试: {email}")
            final_result = attempt_runner()

            if is_manual_activation_cancel_requested(normalized_email) and not final_result.success and final_result.stage != "cancelled":
                final_result = _build_manual_activation_cancelled_result(action_label)

            if final_result.success:
                break
            if _should_stop_manual_activation_retry(final_result):
                break
            if attempt_index < max_attempts:
                print(f"⚠️ {action_label} 第 {attempt_index}/{max_attempts} 次失败，准备继续重试: {final_result.message or final_result.status or final_result.stage}")
                if _wait_before_next_manual_activation_attempt(action_label, normalized_email, attempt_index + 1, max_attempts):
                    final_result = _build_manual_activation_cancelled_result(action_label)
                    break

        return _decorate_manual_activation_result(
            action_label,
            final_result,
            actual_attempts,
            max_attempts,
        )
    finally:
        clear_manual_activation_cancel_request(normalized_email)


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


def _normalize_delivery_vendor(vendor: str) -> str:
    """
    规范化发货厂家名称。

    参数:
        vendor: 原始厂家名称
    返回:
        str: 规范化后的厂家名称
        AI by zb
    """
    normalized_vendor = str(vendor or "").strip()
    return normalized_vendor or "咸鱼"


def _build_delivery_mail_content(account_email: str, password: str, vendor: str) -> dict:
    """
    生成发货邮件内容。

    参数:
        account_email: 账号邮箱
        password: 账号密码
        vendor: 厂家名称
    返回:
        dict: 邮件主题与正文
        AI by zb
    """
    subject = f"授权信息 | {account_email}"
    text = (
        f"厂家：{vendor}\n"
        f"账号：{account_email}\n"
        f"密码：{password}\n"
        f"发货时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    html = (
        "<div style=\"font-family:Arial,'PingFang SC','Microsoft YaHei',sans-serif;"
        "line-height:1.7;color:#1f2b44;padding:8px 0;\">"
        f"<p><strong>厂家：</strong>{vendor}</p>"
        f"<p><strong>账号：</strong>{account_email}</p>"
        f"<p><strong>密码：</strong>{password}</p>"
        f"<p><strong>发货时间：</strong>{time.strftime('%Y-%m-%d %H:%M:%S')}</p>"
        "<p style=\"color:#6b7280;font-size:12px;\">本邮件由系统自动发送，请妥善保管账号信息。</p>"
        "</div>"
    )
    return {
        "subject": subject,
        "text": text,
        "html": html,
    }


def _save_delivery_info(
    email: str,
    delivered: bool,
    vendor: str,
    delivery_email: str,
    message: str,
    temp_access_url: str = "",
    mail_id: str = "",
) -> dict:
    """
    写回账号发货信息。

    参数:
        email: 账号邮箱
        delivered: 是否已完成发货
        vendor: 厂家名称
        delivery_email: 发货目标邮箱
        message: 发货说明
        temp_access_url: 临时访问链接
        mail_id: 邮件服务返回的发件 ID
    返回:
        dict: 更新后的账号记录
        AI by zb
    """
    normalized_vendor = _normalize_delivery_vendor(vendor)
    return upsert_account_record(
        email,
        {
            "deliveryInfo": {
                "delivered": bool(delivered),
                "vendor": normalized_vendor,
                "targetEmail": str(delivery_email or "").strip(),
                "status": "已发货" if delivered else "发货失败",
                "message": str(message or "").strip(),
                "tempAccessUrl": str(temp_access_url or "").strip(),
                "mailId": str(mail_id or "").strip(),
                "deliveredAt": time.strftime("%Y%m%d_%H%M%S") if delivered else "",
            }
        },
    )


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


def run_delivery_for_account(
    email: str,
    vendor: str = "咸鱼",
) -> AccountDeliveryResult:
    """
    向指定邮箱发送账号密码并生成临时访问链接。

    参数:
        email: 账号邮箱
        vendor: 厂家名称
    返回:
        AccountDeliveryResult: 发货结果
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        return AccountDeliveryResult(success=False, stage="account", message="账号不存在")

    normalized_delivery_email = str(email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized_delivery_email):
        return AccountDeliveryResult(success=False, stage="delivery_email", message="当前账号邮箱格式不正确，无法发货")

    password = str(account.get("password") or "").strip()
    if not password or password == "N/A":
        return AccountDeliveryResult(success=False, stage="password", message="账号未保存可用密码，无法发货")

    normalized_vendor = _normalize_delivery_vendor(vendor)
    mail_content = _build_delivery_mail_content(email, password, normalized_vendor)

    send_result = send_single_email(
        to_email=normalized_delivery_email,
        subject=mail_content["subject"],
        html=mail_content["html"],
        text=mail_content["text"],
        from_email="auth@joini.cloud",
        from_name="授权信息",
    )
    if not bool(send_result.get("success")):
        _save_delivery_info(
            email,
            delivered=False,
            vendor=normalized_vendor,
            delivery_email=normalized_delivery_email,
            message=str(send_result.get("message") or "发货邮件发送失败").strip(),
        )
        return AccountDeliveryResult(
            success=False,
            delivered=False,
            stage="send_mail",
            message=str(send_result.get("message") or "发货邮件发送失败").strip(),
            vendor=normalized_vendor,
            delivery_email=normalized_delivery_email,
        )

    temp_access_result = create_temp_access_url(
        normalized_delivery_email,
        extra_query_params={
            "address": normalized_delivery_email,
            "email": normalized_delivery_email,
        },
    )
    temp_access_url = str(temp_access_result.get("url") or "").strip()
    temp_access_ready = bool(temp_access_result.get("success")) and bool(temp_access_url)
    if temp_access_ready:
        delivery_message = f"已向 {normalized_delivery_email} 发货，并生成临时访问链接"
    else:
        delivery_message = (
            f"已向 {normalized_delivery_email} 发货，但临时访问链接生成失败"
            f"{'：' + str(temp_access_result.get('message') or '').strip() if str(temp_access_result.get('message') or '').strip() else ''}"
        )

    _save_delivery_info(
        email,
        delivered=True,
        vendor=normalized_vendor,
        delivery_email=normalized_delivery_email,
        message=delivery_message,
        temp_access_url=temp_access_url,
        mail_id=str(send_result.get("id") or "").strip(),
    )
    return AccountDeliveryResult(
        success=True,
        delivered=True,
        stage="deliver",
        message=delivery_message,
        vendor=normalized_vendor,
        delivery_email=normalized_delivery_email,
        temp_access_url=temp_access_url,
        temp_access_ready=temp_access_ready,
        mail_id=str(send_result.get("id") or "").strip(),
    )


def run_manual_account_create(email: str, password: str = "", access_token: str = "") -> dict:
    """
    手动新增账号记录。

    参数:
        email: 邮箱地址
        password: 账号密码
        access_token: accessToken
    返回:
        dict: 新增后的账号记录
        AI by zb
    """
    normalized_email = str(email or "").strip().lower()
    normalized_password = str(password or "").strip()
    normalized_access_token = str(access_token or "").strip()

    if not normalized_email:
        raise ValueError("邮箱不能为空")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized_email):
        raise ValueError("邮箱格式不正确")
    if not normalized_password and not normalized_access_token:
        raise ValueError("密码和 accessToken 不能同时为空")
    if get_account_record(normalized_email):
        raise ValueError("账号已存在，请勿重复添加")

    return upsert_account_record(
        normalized_email,
        {
            "password": normalized_password or "N/A",
            "status": "手动导入",
            "registrationStatus": "success",
            "overallStatus": "success",
            "accessToken": normalized_access_token,
            "plusCalled": False,
            "plusSuccess": False,
            "plusState": "idle",
            "plusStatus": "未调用",
            "plusMessage": "",
            "plusRequestId": "",
            "plusCalledAt": "",
            "sub2apiUploaded": False,
            "sub2apiState": "pending",
            "sub2apiStatus": "待上传",
            "sub2apiMessage": "",
            "sub2apiUploadedAt": "",
            "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
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
            lambda: run_plus_binding_with_access_token(
                stored_access_token,
                use_cache=False,
                should_cancel=lambda: is_manual_activation_cancel_requested(email),
            ),
        )
        _save_plus_result(email, result, access_token=stored_access_token)
        return result
    elif stored_access_token:
        print(f"ℹ️ 当前 Plus 模式不支持仅凭 accessToken 重试，将改为浏览器登录模式: {email}")

    if not password or password == "N/A":
        result = PlusActivationResult(success=False, stage="login", message="账号未保存可用密码，无法重新登录提取 token")
        _save_plus_result(email, result, access_token=stored_access_token)
        return result

    driver = None
    def attempt_runner() -> PlusActivationResult:
        nonlocal driver
        driver = None
        try:
            print(f"🌐 尝试浏览器登录后执行当前配置的 Plus 绑定流程: {email}")
            driver = create_driver(headless=not cfg.browser.show_browser_window)
            if not login(driver, email, password):
                return PlusActivationResult(success=False, stage="login", message="浏览器登录失败")
            return run_plus_binding_with_browser_session(
                driver,
                use_cache=False,
                should_cancel=lambda: is_manual_activation_cancel_requested(email),
            )
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
        result = _run_manual_activation_with_retries(
            "Team激活",
            email,
            lambda: activate_team_with_access_token(
                stored_access_token,
                use_cache=False,
                should_cancel=lambda: is_manual_activation_cancel_requested(email),
            ),
        )
        _save_plus_result(email, result, access_token=stored_access_token, action_label="Team")
        return result

    if not password or password == "N/A":
        result = PlusActivationResult(success=False, stage="login", message="账号未保存可用密码，无法重新登录提取 token")
        _save_plus_result(email, result, access_token=stored_access_token, action_label="Team")
        return result

    driver = None
    def attempt_runner() -> PlusActivationResult:
        nonlocal driver
        driver = None
        try:
            print(f"🌐 尝试浏览器登录后执行 Team 激活流程: {email}")
            driver = create_driver(headless=not cfg.browser.show_browser_window)
            if not login(driver, email, password):
                return PlusActivationResult(success=False, stage="login", message="浏览器登录失败")
            return activate_team_with_browser_session(
                driver,
                use_cache=False,
                should_cancel=lambda: is_manual_activation_cancel_requested(email),
            )
        except Exception as exc:
            return PlusActivationResult(success=False, stage="login", message=str(exc))
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None

    result = _run_manual_activation_with_retries("Team激活", email, attempt_runner)
    _save_plus_result(email, result, action_label="Team")
    return result


def refresh_activation_status_for_account(email: str) -> dict:
    """
    使用 requestId 查询远端激活状态，并同步回账号记录。

    参数:
        email: 邮箱地址
    返回:
        dict: 更新后的账号记录
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        raise ValueError("账号不存在")

    request_id = str(account.get("plusRequestId") or "").strip()
    if not request_id:
        raise ValueError("当前账号没有可查询的激活 requestId")

    action_label = _infer_activation_action_label(account)
    result = query_activation_request_result(
        request_id=request_id,
        action_label=action_label,
        access_token=str(account.get("accessToken") or "").strip(),
    )
    updated_account = _save_plus_result(
        email,
        result,
        access_token=str(account.get("accessToken") or "").strip(),
        action_label=action_label,
    )
    if (
        action_label == "Plus"
        and result.success
        and is_sub2api_auto_upload_enabled()
        and not bool(updated_account.get("sub2apiUploaded"))
    ):
        run_sub2api_upload_for_account(email)
        refreshed_account = get_account_record(email)
        if refreshed_account:
            return refreshed_account
    return updated_account


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

    normalized_email = _normalize_activation_email(email)
    request_manual_activation_cancel(normalized_email)

    try:
        result = cancel_active_activation()
    except Exception as exc:
        error_message = str(exc or "").strip()
        result = {
            "requestId": "",
            "activeAction": "",
            "message": (
                "已停止后续重试，当前没有进行中的远端激活任务"
                if "当前没有进行中的激活任务" in error_message
                else f"已停止后续重试；远端取消请求失败: {error_message or '未知错误'}"
            ),
        }

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
