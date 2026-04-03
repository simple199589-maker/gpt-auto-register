"""
ChatGPT 账号自动注册脚本
主程序入口

使用方法:
    1. 修改 config.py 中的配置
    2. 运行: python main.py

依赖安装:
    pip install undetected-chromedriver selenium requests

功能:
    - 自动创建临时邮箱（基于 cloudflare_temp_email）
    - 自动完成 ChatGPT 注册流程
    - 自动提取验证码
    - 批量注册支持
"""

import time
import random
from typing import Callable

from app.config import (
    TOTAL_ACCOUNTS,
    BATCH_INTERVAL_MIN,
    BATCH_INTERVAL_MAX,
    EMAIL_WAIT_TIMEOUT,
    cfg,
)
from app.account_actions import (
    is_plus_auto_activation_enabled,
    is_sub2api_auto_upload_enabled,
    run_sub2api_upload_for_account,
)
from app.plus_activation_api import fetch_access_token, fetch_session_info
from app.plus_binding import (
    is_access_token_plus_binding_mode,
    run_plus_binding_with_access_token,
    run_plus_binding_with_browser_session,
)
from app.utils import (
    generate_random_password,
    get_account_record,
    save_to_txt,
    update_account_status,
    upsert_account_record,
)
from app.email_service import (
    create_temp_email,
    create_mailbox_marker,
    wait_for_verification_email_with_marker
)
from app.browser import (
    click_resend_verification_email,
    create_driver,
    fill_signup_form,
    enter_verification_code,
    fill_profile_info,
    login,
)
from app.browser._legacy import open_first_reachable_url, CHATGPT_HOME_URLS
from selenium.webdriver.common.by import By

VERIFICATION_EMAIL_RESEND_AFTER_SECONDS = 30
PERSISTED_SUCCESS_DRIVERS = []


def keep_browser_open_after_success(driver) -> None:
    """
    在注册成功后保留浏览器实例，避免析构阶段自动关闭窗口。

    参数:
        driver: 浏览器驱动实例
    返回:
        None
        AI by zb
    """
    if not driver:
        return

    setattr(driver, "_skip_auto_quit", True)
    PERSISTED_SUCCESS_DRIVERS.append(driver)
    print("🪟 注册已完成，浏览器窗口保持打开。")


def should_keep_browser_open_after_registration() -> bool:
    """
    判断注册成功后是否暂时保留浏览器窗口。

    返回:
        bool: 是否在当前轮注册完成后暂时保留浏览器窗口
        AI by zb
    """
    return bool(cfg.browser.keep_browser_open_after_registration)


def close_persisted_success_browsers() -> None:
    """
    关闭上一轮注册成功后暂时保留的浏览器窗口。

    返回:
        None
        AI by zb
    """
    if not PERSISTED_SUCCESS_DRIVERS:
        return

    print("🔒 下一轮开始前，先关闭上一轮保留的浏览器...")
    while PERSISTED_SUCCESS_DRIVERS:
        driver = PERSISTED_SUCCESS_DRIVERS.pop()
        try:
            setattr(driver, "_skip_auto_quit", False)
            driver.quit()
        except Exception:
            pass


def wait_verification_code_with_single_resend(
    driver,
    email_context_token,
    since_marker,
    timeout: int = EMAIL_WAIT_TIMEOUT,
):
    """
    分阶段等待验证码邮件，首次等待 30 秒仍未收到时自动点击一次重发。

    参数:
        driver: 浏览器驱动
        email_context_token: 邮箱上下文令牌
        since_marker: 首次等待的时间标记
        timeout: 总等待时长（秒）

    返回:
        str | None: 验证码
        AI by zb
    """
    total_timeout = max(int(timeout or EMAIL_WAIT_TIMEOUT), 1)
    first_wait_seconds = min(VERIFICATION_EMAIL_RESEND_AFTER_SECONDS, total_timeout)

    verification_code = wait_for_verification_email_with_marker(
        email_context_token,
        since_marker=since_marker,
        timeout=first_wait_seconds,
    )
    if verification_code or total_timeout <= first_wait_seconds:
        return verification_code

    print(f"⚠️ {first_wait_seconds}秒内未收到验证码邮件，准备点击一次重新发送电子邮件")
    resend_marker = create_mailbox_marker()
    resend_clicked = click_resend_verification_email(driver)
    remaining_timeout = max(total_timeout - first_wait_seconds, 1)

    if not resend_clicked:
        print("⚠️ 重新发送电子邮件点击失败，将继续等待原验证码邮件")
        return wait_for_verification_email_with_marker(
            email_context_token,
            since_marker=since_marker,
            timeout=remaining_timeout,
        )

    return wait_for_verification_email_with_marker(
        email_context_token,
        since_marker=resend_marker,
        timeout=remaining_timeout,
    )


def handle_sub2api_auto_upload(email: str, status_when_disabled: str, report_callback=None):
    """
    根据当前配置执行或跳过 Sub2Api 自动上传。

    参数:
        email: 邮箱地址
        status_when_disabled: 自动上传关闭时写回的总状态
        report_callback: 可选状态回调
    返回:
        object | None: 上传结果；若未启用自动上传则返回 None
        AI by zb
    """
    if is_sub2api_auto_upload_enabled():
        print("\n" + "-" * 30)
        print("📤 开始自动上传 Sub2Api")
        print("-" * 30)
        upload_result = run_sub2api_upload_for_account(email)
        if report_callback:
            report_callback("sub2api_uploaded" if upload_result.uploaded else "sub2api_upload_failed")
        return upload_result

    update_account_status(
        email,
        status_when_disabled,
        extra={
            "sub2apiUploaded": False,
            "sub2apiState": "disabled",
            "sub2apiStatus": "自动上传未启用",
            "sub2apiMessage": "配置中关闭了自动上传",
            "sub2apiAutoUploadEnabled": False,
        },
    )
    if report_callback:
        report_callback("sub2api_auto_upload_disabled")
    return None


def persist_registration_failure(
    email: str,
    password: str,
    mailbox_context: str,
    status: str,
    error_message: str,
    report_callback=None,
):
    """
    将注册阶段失败写回账号记录。

    参数:
        email: 邮箱地址
        password: 账号密码
        mailbox_context: 邮箱上下文
        status: 展示状态
        error_message: 失败原因
        report_callback: 可选回调
        AI by zb
    """
    update_account_status(
        email,
        status,
        password=password,
        extra={
            "mailboxContext": mailbox_context,
            "registrationStatus": "failed",
            "overallStatus": "failed",
            "lastError": error_message or status,
            "plusCalled": False,
            "plusSuccess": False,
            "plusState": "idle",
            "plusStatus": "未调用",
            "plusMessage": "",
            "sub2apiUploaded": False,
            "sub2apiState": "pending",
            "sub2apiStatus": "未上传",
            "sub2apiMessage": "",
            "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
        },
    )
    if report_callback:
        report_callback("registration_failed")


def detect_registration_resume_stage(driver) -> str:
    """
    检测当前页面所处的注册补偿阶段。

    参数:
        driver: 浏览器驱动
    返回:
        str: `verification` / `profile` / `home` / 空字符串
        AI by zb
    """
    try:
        verification_inputs = driver.find_elements(
            By.CSS_SELECTOR,
            'input[name="code"], input[placeholder*="代码"], input[aria-label*="代码"]',
        )
        if any(element.is_displayed() for element in verification_inputs):
            return "verification"
    except Exception:
        pass

    try:
        profile_inputs = driver.find_elements(
            By.CSS_SELECTOR,
            'input[name="name"], input[autocomplete="name"]',
        )
        if any(element.is_displayed() for element in profile_inputs):
            return "profile"
    except Exception:
        pass

    current_url = str(getattr(driver, "current_url", "") or "").lower()
    if current_url and "auth" not in current_url:
        return "home"
    return ""


def continue_registration_from_current_page(
    driver,
    mailbox_context: str,
    report_callback: Callable[[str], None] | None = None,
):
    """
    从当前页面继续执行剩余注册步骤。

    参数:
        driver: 浏览器驱动
        mailbox_context: 邮箱上下文
        report_callback: 可选回调
    返回:
        tuple[bool, str, str]: 是否成功、阶段、消息
        AI by zb
    """
    stage = detect_registration_resume_stage(driver)

    if stage == "verification":
        verification_marker = create_mailbox_marker()
        verification_code = wait_verification_code_with_single_resend(
            driver,
            mailbox_context,
            since_marker=verification_marker,
        )
        if not verification_code:
            return False, "verification", "未获取到验证码"
        if not enter_verification_code(driver, verification_code):
            return False, "verification", "输入验证码失败"
        if report_callback:
            report_callback("enter_code")
        stage = detect_registration_resume_stage(driver)

    if stage == "profile":
        if not fill_profile_info(driver):
            return False, "profile", "填写个人资料失败"
        if report_callback:
            report_callback("fill_profile")
        stage = detect_registration_resume_stage(driver)

    if stage == "home":
        return True, "completed", "注册已完成"

    return False, "unknown", f"未识别到可继续的注册页面: {getattr(driver, 'current_url', '')}"


def persist_browser_session_context_for_account(
    driver,
    email: str,
    mailbox_context: str,
) -> dict:
    """
    在注册完成后尽量提取并留存当前账号的浏览器会话上下文。

    参数:
        driver: 浏览器驱动
        email: 邮箱地址
        mailbox_context: 邮箱上下文
    返回:
        dict: 包含 `access_token` 与 `session_info` 的结果
        AI by zb
    """
    access_token = ""
    session_info = {}

    try:
        access_token = str(fetch_access_token(driver) or "").strip()
    except Exception as exc:
        print(f"⚠️ 注册完成后提取 accessToken 失败: {exc}")

    try:
        session_info = fetch_session_info(driver) or {}
    except Exception as exc:
        print(f"⚠️ 注册完成后提取 session 信息失败: {exc}")

    if access_token or session_info:
        upsert_account_record(
            email,
            {
                "mailboxContext": mailbox_context,
                "accessToken": access_token,
                "sessionInfo": session_info,
            },
        )

    return {
        "access_token": access_token,
        "session_info": session_info,
    }


def complete_registered_account_flow(
    driver,
    email: str,
    password: str,
    mailbox_context: str,
    report_callback: Callable[[str], None] | None = None,
    heading: str = "🎉 注册成功！",
):
    """
    在注册完成后执行统一的账号落库与后续自动流程。

    参数:
        driver: 浏览器驱动
        email: 邮箱地址
        password: 账号密码
        mailbox_context: 邮箱上下文
        report_callback: 可选回调
        heading: 提示标题
        AI by zb
    """
    save_to_txt(
        email,
        password,
        "已注册",
        extra={
            "mailboxContext": mailbox_context,
            "registrationStatus": "success",
            "overallStatus": "success",
            "plusCalled": False,
            "plusSuccess": False,
            "plusState": "idle",
            "sub2apiUploaded": False,
            "sub2apiState": "pending",
            "sub2apiStatus": "待上传",
            "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
            "lastError": "",
        },
    )

    print("\n" + "=" * 50)
    print(heading)
    print(f"   邮箱: {email}")
    print(f"   密码: {password}")
    print("=" * 50)

    print("⏳ 等待页面稳定...")
    time.sleep(5)
    if report_callback:
        report_callback("registered")

    browser_session_context = persist_browser_session_context_for_account(
        driver,
        email,
        mailbox_context,
    )
    saved_access_token = str(browser_session_context.get("access_token") or "").strip()
    saved_session_info = browser_session_context.get("session_info") or {}

    if is_plus_auto_activation_enabled():
        print("\n" + "-" * 30)
        print("🚀 开始执行 Plus 绑定流程")
        print("-" * 30)

        if is_access_token_plus_binding_mode() and saved_access_token:
            print("♻️ 注册成功后复用已保存 accessToken 执行 Plus 激活")
            activation_result = run_plus_binding_with_access_token(saved_access_token)
            if not activation_result.session_info and saved_session_info:
                activation_result.session_info = saved_session_info
            if isinstance(activation_result.response_data, dict) and saved_session_info:
                activation_result.response_data["sessionInfo"] = saved_session_info
        else:
            if is_access_token_plus_binding_mode():
                print("ℹ️ 当前未留存可用 accessToken，将回退为浏览器会话提取后再激活")
            activation_result = run_plus_binding_with_browser_session(driver)

        if activation_result.success:
            print("🎉 Plus 绑定流程执行成功！")
            if activation_result.request_id:
                print(f"   requestId: {activation_result.request_id}")
            if activation_result.status:
                print(f"   状态: {activation_result.status}")
            update_account_status(
                email,
                "已激活Plus",
                access_token=activation_result.access_token or None,
                extra={
                    "mailboxContext": mailbox_context,
                    "registrationStatus": "success",
                    "overallStatus": "success",
                    "sessionInfo": activation_result.session_info,
                    "plusCalled": True,
                    "plusSuccess": True,
                    "plusState": "success",
                    "plusStatus": activation_result.status or "已激活Plus",
                    "plusMessage": activation_result.message,
                    "plusRequestId": activation_result.request_id,
                    "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
                    "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
                    "lastError": "",
                },
            )
            if report_callback:
                report_callback("plus_activated")
            handle_sub2api_auto_upload(email, "已激活Plus，未上传Sub2Api", report_callback=report_callback)
            return

        if str(activation_result.stage or "").strip().lower() == "submitted":
            print("📨 Plus 激活请求已提交，等待远端任务完成")
            if activation_result.request_id:
                print(f"   requestId: {activation_result.request_id}")
            if activation_result.status:
                print(f"   状态: {activation_result.status}")
            update_account_status(
                email,
                "Plus激活已提交",
                access_token=activation_result.access_token or None,
                extra={
                    "mailboxContext": mailbox_context,
                    "registrationStatus": "success",
                    "overallStatus": "pending",
                    "sessionInfo": activation_result.session_info,
                    "plusCalled": True,
                    "plusSuccess": False,
                    "plusState": "pending",
                    "plusStatus": activation_result.status or "处理中",
                    "plusMessage": activation_result.message,
                    "plusRequestId": activation_result.request_id,
                    "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
                    "sub2apiUploaded": False,
                    "sub2apiState": "pending",
                    "sub2apiStatus": "待上传",
                    "sub2apiMessage": "等待 Plus 激活完成后再触发上传",
                    "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
                    "lastError": "",
                },
            )
            if report_callback:
                report_callback("plus_activation_submitted")
            return

        print(f"⚠️ Plus 绑定流程失败: {activation_result.message}")
        if activation_result.stage == "config":
            update_account_status(
                email,
                "Plus配置缺失",
                access_token=activation_result.access_token or None,
                extra={
                    "mailboxContext": mailbox_context,
                    "registrationStatus": "success",
                    "overallStatus": "failed",
                    "sessionInfo": activation_result.session_info,
                    "plusCalled": True,
                    "plusSuccess": False,
                    "plusState": "failed",
                    "plusStatus": "Plus配置缺失",
                    "plusMessage": activation_result.message,
                    "plusRequestId": activation_result.request_id,
                    "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
                    "sub2apiUploaded": False,
                    "sub2apiState": "pending",
                    "sub2apiStatus": "未上传",
                    "sub2apiMessage": "Plus 未成功，未触发上传",
                    "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
                    "lastError": activation_result.message or "Plus配置缺失",
                },
            )
            if report_callback:
                report_callback("activation_config_missing")
            return

        if activation_result.stage == "fetch_token":
            update_account_status(
                email,
                "Token获取失败",
                access_token=activation_result.access_token or None,
                extra={
                    "mailboxContext": mailbox_context,
                    "registrationStatus": "success",
                    "overallStatus": "failed",
                    "sessionInfo": activation_result.session_info,
                    "plusCalled": True,
                    "plusSuccess": False,
                    "plusState": "failed",
                    "plusStatus": "Token获取失败",
                    "plusMessage": activation_result.message,
                    "plusRequestId": activation_result.request_id,
                    "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
                    "sub2apiUploaded": False,
                    "sub2apiState": "pending",
                    "sub2apiStatus": "未上传",
                    "sub2apiMessage": "Plus 未成功，未触发上传",
                    "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
                    "lastError": activation_result.message or "Token获取失败",
                },
            )
            if report_callback:
                report_callback("token_fetch_failed")
            return

        update_account_status(
            email,
            "Plus绑定失败",
            access_token=activation_result.access_token or None,
            extra={
                "mailboxContext": mailbox_context,
                "registrationStatus": "success",
                "overallStatus": "failed",
                "sessionInfo": activation_result.session_info,
                "plusCalled": True,
                "plusSuccess": False,
                "plusState": "failed",
                "plusStatus": activation_result.status or "Plus绑定失败",
                "plusMessage": activation_result.message,
                "plusRequestId": activation_result.request_id,
                "plusCalledAt": time.strftime("%Y%m%d_%H%M%S"),
                "sub2apiUploaded": False,
                "sub2apiState": "pending",
                "sub2apiStatus": "未上传",
                "sub2apiMessage": "Plus 未成功，未触发上传",
                "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
                "lastError": activation_result.message or "Plus绑定失败",
            },
        )
        if report_callback:
            report_callback("plus_binding_failed")
        return

    print("\n" + "-" * 30)
    print("⏭️ Plus 自动激活已关闭，直接进入 Sub2Api 步骤")
    print("-" * 30)
    update_account_status(
        email,
        "已注册，跳过Plus",
        extra={
            "mailboxContext": mailbox_context,
            "registrationStatus": "success",
            "overallStatus": "success",
            "plusCalled": False,
            "plusSuccess": False,
            "plusState": "disabled",
            "plusStatus": "已关闭",
            "plusMessage": "配置中关闭了 Plus 激活，已直接进入 Sub2Api 步骤",
            "plusRequestId": "",
            "plusCalledAt": "",
            "sub2apiUploaded": False,
            "sub2apiState": "pending",
            "sub2apiStatus": "待上传",
            "sub2apiMessage": "",
            "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
            "lastError": "",
        },
    )
    if report_callback:
        report_callback("plus_auto_activation_disabled")
    handle_sub2api_auto_upload(email, "已注册，跳过Plus", report_callback=report_callback)


def run_registration_retry_for_account(email: str, monitor_callback=None) -> dict:
    """
    对未完成注册的账号执行补偿注册。

    参数:
        email: 邮箱地址
        monitor_callback: 可选监控回调
    返回:
        dict: 执行结果
        AI by zb
    """
    account = get_account_record(email)
    if not account:
        return {"success": False, "stage": "account", "message": "账号不存在"}

    if str(account.get("registrationStatus") or "").strip().lower() == "success":
        return {"success": False, "stage": "account", "message": "账号已注册完成，无需继续注册"}

    password = str(account.get("password") or "").strip()
    if not password or password == "N/A":
        return {"success": False, "stage": "account", "message": "账号未保存可用密码，无法继续注册"}

    mailbox_context = str(account.get("mailboxContext") or f"mailbox::{email}").strip()
    driver = None
    success = False

    def _report(step_name):
        if monitor_callback and driver:
            monitor_callback(driver, step_name)

    try:
        update_account_status(
            email,
            "继续注册中",
            extra={
                "mailboxContext": mailbox_context,
                "registrationStatus": "pending",
                "overallStatus": "pending",
                "lastError": "",
            },
        )

        driver = create_driver(
            headless=not cfg.browser.show_browser_window,
            detach=should_keep_browser_open_after_registration(),
        )
        _report("init_browser")
        open_first_reachable_url(driver, CHATGPT_HOME_URLS, "register")
        _report("open_page")

        print("\n" + "-" * 30)
        print(f"🔁 开始继续注册账号: {email}")
        print("-" * 30)

        if fill_signup_form(driver, email, password):
            _report("fill_form")
            resume_success, stage, message = continue_registration_from_current_page(
                driver,
                mailbox_context,
                report_callback=_report,
            )
            if resume_success:
                complete_registered_account_flow(
                    driver,
                    email,
                    password,
                    mailbox_context,
                    report_callback=_report,
                    heading="🎉 补偿注册成功！",
                )
                success = True
                return {"success": True, "stage": "completed", "message": "继续注册成功"}
            print(f"⚠️ 注册页补偿未完成，尝试登录兜底: {message}")
        else:
            print("⚠️ 注册页补偿失败，尝试登录兜底")

        if not login(driver, email, password):
            persist_registration_failure(
                email,
                password,
                mailbox_context,
                "继续注册失败",
                "浏览器登录失败",
                report_callback=_report,
            )
            return {"success": False, "stage": "login", "message": "浏览器登录失败"}

        _report("login")
        resume_success, stage, message = continue_registration_from_current_page(
            driver,
            mailbox_context,
            report_callback=_report,
        )
        if not resume_success:
            persist_registration_failure(
                email,
                password,
                mailbox_context,
                "继续注册失败",
                message,
                report_callback=_report,
            )
            return {"success": False, "stage": stage, "message": message}

        complete_registered_account_flow(
            driver,
            email,
            password,
            mailbox_context,
            report_callback=_report,
            heading="🎉 补偿注册成功！",
        )
        success = True
        return {"success": True, "stage": "completed", "message": "继续注册成功"}
    except InterruptedError:
        update_account_status(
            email,
            "继续注册中断",
            extra={
                "registrationStatus": "failed",
                "overallStatus": "failed",
                "lastError": "用户中断继续注册",
            },
        )
        return {"success": False, "stage": "interrupted", "message": "用户中断继续注册"}
    except Exception as exc:
        persist_registration_failure(
            email,
            password,
            mailbox_context,
            "继续注册失败",
            str(exc),
            report_callback=_report,
        )
        return {"success": False, "stage": "retry", "message": str(exc)}
    finally:
        if driver:
            if success and should_keep_browser_open_after_registration():
                keep_browser_open_after_success(driver)
            else:
                print("🔒 正在关闭浏览器...")
                driver.quit()


def register_one_account(monitor_callback=None):
    """
    注册单个账号
    :param monitor_callback: 回调函数 func(driver, step_name)，用于截图和中断检查
    
    返回:
        tuple: (邮箱, 密码, 是否成功)
    """
    driver = None
    email = None
    password = None
    success = False
    mailbox_context = ""
    
    # 辅助函数：执行回调
    def _report(step_name):
        if monitor_callback and driver:
            monitor_callback(driver, step_name)

    try:
        # 1. 创建临时邮箱
        print("📧 正在创建临时邮箱...")
        email, email_context_token = create_temp_email()
        if not email:
            print("❌ 创建邮箱失败，终止注册")
            return None, None, False
        mailbox_context = str(email_context_token or f"mailbox::{email}")
        
        # 2. 生成随机密码
        password = generate_random_password()
        upsert_account_record(
            email,
            {
                "password": password,
                "status": "注册中",
                "registrationStatus": "pending",
                "overallStatus": "pending",
                "lastError": "",
                "mailboxContext": mailbox_context,
                "sub2apiAutoUploadEnabled": is_sub2api_auto_upload_enabled(),
            },
        )
        
        # 3. 初始化浏览器
        driver = create_driver(
            headless=not cfg.browser.show_browser_window,
            detach=should_keep_browser_open_after_registration(),
        )
        _report("init_browser")
        
        # 4. 打开注册页面
        open_first_reachable_url(driver, CHATGPT_HOME_URLS, "register")
        _report("open_page")
        
        # 5. 填写注册表单（邮箱和密码）
        verification_email_marker = create_mailbox_marker()
        if not fill_signup_form(driver, email, password):
            print("❌ 填写注册表单失败")
            persist_registration_failure(
                email,
                password,
                mailbox_context,
                "注册失败",
                "填写注册表单失败",
                report_callback=_report,
            )
            return email, password, False
        _report("fill_form")
        
        # 6. 等待验证邮件
        time.sleep(5)
        verification_code = wait_verification_code_with_single_resend(
            driver,
            email_context_token,
            since_marker=verification_email_marker,
        )
        
        # 如果没有自动获取到验证码，提示手动输入
        if not verification_code:
            print("⚠️ 未自动获取验证码，尝试请求用户输入...")
            # 可以在这里扩展手动输入回调，暂略
            # verification_code = input("⌨️ 请手动输入验证码: ").strip()
        
        if not verification_code:
            print("❌ 未获取到验证码，终止注册")
            persist_registration_failure(
                email,
                password,
                mailbox_context,
                "注册失败",
                "未获取到验证码",
                report_callback=_report,
            )
            return email, password, False
        
        # 7. 输入验证码
        if not enter_verification_code(driver, verification_code):
            print("❌ 输入验证码失败")
            persist_registration_failure(
                email,
                password,
                mailbox_context,
                "注册失败",
                "输入验证码失败",
                report_callback=_report,
            )
            return email, password, False
        _report("enter_code")
        
        # 8. 填写个人资料
        if not fill_profile_info(driver):
            print("❌ 填写个人资料失败")
            persist_registration_failure(
                email,
                password,
                mailbox_context,
                "注册失败",
                "填写个人资料失败",
                report_callback=_report,
            )
            return email, password, False
        _report("fill_profile")
        
        complete_registered_account_flow(
            driver,
            email,
            password,
            mailbox_context,
            report_callback=_report,
            heading="🎉 注册成功！",
        )
        success = True
        time.sleep(5)
        
    except InterruptedError:
        print("🛑 任务已被用户强制中断")
        if email:
            update_account_status(
                email,
                "用户中断",
                extra={
                    "registrationStatus": "failed",
                    "overallStatus": "failed",
                    "lastError": "用户中断",
                },
            )
        return email, password, False
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        if email and password:
            existing_record = get_account_record(email) or {}
            registration_status = str(existing_record.get("registrationStatus") or "failed")
            update_account_status(
                email,
                f"错误: {str(e)[:50]}",
                extra={
                    "registrationStatus": registration_status if registration_status in {"pending", "success"} else "failed",
                    "overallStatus": "failed",
                    "lastError": str(e),
                },
            )
    
    finally:
        if driver:
            if success and should_keep_browser_open_after_registration():
                keep_browser_open_after_success(driver)
            else:
                print("🔒 正在关闭浏览器...")
                driver.quit()
    
    return email, password, success
    



def run_batch():
    """
    批量注册账号
    """
    print("\n" + "=" * 60)
    print(f"🚀 开始批量注册，目标数量: {TOTAL_ACCOUNTS}")
    print("=" * 60 + "\n")

    print("\n⚠️  免责声明：本项目仅供学习研究使用。请勿用于商业用途或违规操作。")
    print("⚠️  使用者需自行承担因违规使用导致的一切后果。\n")
    time.sleep(2)
    
    success_count = 0
    fail_count = 0
    registered_accounts = []
    
    for i in range(TOTAL_ACCOUNTS):
        close_persisted_success_browsers()

        print("\n" + "#" * 60)
        print(f"📝 正在注册第 {i + 1}/{TOTAL_ACCOUNTS} 个账号")
        print("#" * 60 + "\n")
        
        email, password, success = register_one_account()
        
        if success:
            success_count += 1
            registered_accounts.append((email, password))
        else:
            fail_count += 1
        
        # 显示进度
        print("\n" + "-" * 40)
        print(f"📊 当前进度: {i + 1}/{TOTAL_ACCOUNTS}")
        print(f"   ✅ 成功: {success_count}")
        print(f"   ❌ 失败: {fail_count}")
        print("-" * 40)
        
        # 如果还有下一个，等待随机时间
        if i < TOTAL_ACCOUNTS - 1:
            close_persisted_success_browsers()
            wait_time = random.randint(BATCH_INTERVAL_MIN, BATCH_INTERVAL_MAX)
            print(f"\n⏳ 等待 {wait_time} 秒后继续下一个注册...")
            time.sleep(wait_time)
    
    # 最终统计
    print("\n" + "=" * 60)
    print("🏁 批量注册完成")
    print("=" * 60)
    print(f"   总计: {TOTAL_ACCOUNTS}")
    print(f"   ✅ 成功: {success_count}")
    print(f"   ❌ 失败: {fail_count}")
    
    if registered_accounts:
        print("\n📋 成功注册的账号:")
        for email, password in registered_accounts:
            print(f"   - {email}")
    
    print("=" * 60)


if __name__ == "__main__":
    run_batch()
