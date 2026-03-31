"""
Plus 绑定策略分发。
AI by zb
"""

from __future__ import annotations

from typing import Dict, Tuple

from app.browser.subscription import subscribe_plus_trial
from app.config import cfg
from app.plus_activation_api import (
    PlusActivationResult,
    activate_plus_with_access_token as activate_plus_via_api_with_access_token,
    activate_plus_with_browser_session as activate_plus_via_api_with_browser_session,
    fetch_access_token,
    fetch_session_info,
)


PLUS_MODE_ACTIVATION_API = "activation_api"
PLUS_MODE_LEGACY_BROWSER = "legacy_browser"
_PLUS_MODE_ALIASES = {
    "api": PLUS_MODE_ACTIVATION_API,
    "activation_api": PLUS_MODE_ACTIVATION_API,
    "activation-api": PLUS_MODE_ACTIVATION_API,
    "legacy": PLUS_MODE_LEGACY_BROWSER,
    "browser": PLUS_MODE_LEGACY_BROWSER,
    "legacy_browser": PLUS_MODE_LEGACY_BROWSER,
    "legacy-browser": PLUS_MODE_LEGACY_BROWSER,
}


def get_plus_binding_mode() -> str:
    """
    读取并规范化当前 Plus 绑定模式。

    返回:
        str: 规范化后的模式值
        AI by zb
    """
    raw_mode = str(cfg.plus.mode or "").strip().lower()
    normalized_mode = _PLUS_MODE_ALIASES.get(raw_mode, PLUS_MODE_ACTIVATION_API)
    if raw_mode and raw_mode not in _PLUS_MODE_ALIASES:
        print(f"⚠️ 未识别的 plus.mode={raw_mode}，已回退为 {PLUS_MODE_ACTIVATION_API}")
    return normalized_mode


def is_access_token_plus_binding_mode() -> bool:
    """
    判断当前 Plus 绑定模式是否支持仅凭 accessToken 执行。

    返回:
        bool: 是否支持 accessToken 模式
        AI by zb
    """
    return get_plus_binding_mode() == PLUS_MODE_ACTIVATION_API


def _try_fetch_browser_session_context(driver) -> Tuple[str, Dict[str, str]]:
    """
    尝试从当前浏览器会话中提取 accessToken 和会话摘要，不阻断后续 Plus 绑定流程。

    参数:
        driver: Selenium WebDriver
    返回:
        Tuple[str, Dict[str, str]]: (accessToken, sessionInfo)
        AI by zb
    """
    access_token = ""
    session_info: Dict[str, str] = {}

    try:
        access_token = fetch_access_token(driver)
    except Exception as exc:
        print(f"⚠️ 提前提取 accessToken 失败，将继续执行当前 Plus 绑定流程: {exc}")

    try:
        session_info = fetch_session_info(driver)
    except Exception as exc:
        print(f"⚠️ 提前提取 session 信息失败，将继续执行当前 Plus 绑定流程: {exc}")

    return access_token, session_info


def bind_plus_with_legacy_browser(driver) -> PlusActivationResult:
    """
    执行旧版浏览器 Plus 绑定流程，并尽量保留当前账号的 session 信息。

    参数:
        driver: Selenium WebDriver
    返回:
        PlusActivationResult: 统一格式的绑定结果
        AI by zb
    """
    access_token, session_info = _try_fetch_browser_session_context(driver)
    response_data = {
        "mode": PLUS_MODE_LEGACY_BROWSER,
        "sessionInfo": session_info,
    }

    print("🚀 当前配置使用旧版浏览器 Plus 绑定流程")
    try:
        success = bool(subscribe_plus_trial(driver))
    except Exception as exc:
        return PlusActivationResult(
            success=False,
            stage="activate",
            access_token=access_token,
            status="旧版浏览器绑定异常",
            message=str(exc),
            response_data=response_data,
            session_info=session_info,
        )

    return PlusActivationResult(
        success=success,
        stage="completed" if success else "activate",
        access_token=access_token,
        status="旧版浏览器绑定成功" if success else "旧版浏览器绑定失败",
        message="旧版浏览器 Plus 绑定完成" if success else "旧版浏览器 Plus 绑定失败",
        response_data=response_data,
        session_info=session_info,
    )


def run_plus_binding_with_access_token(access_token: str, use_cache: bool = True) -> PlusActivationResult:
    """
    按当前配置执行 Plus 绑定；仅在接口激活模式下支持直接使用 accessToken。

    参数:
        access_token: ChatGPT accessToken
    返回:
        PlusActivationResult: 绑定结果
        AI by zb
    """
    if not is_access_token_plus_binding_mode():
        return PlusActivationResult(
            success=False,
            stage="mode",
            access_token=str(access_token or "").strip(),
            message="当前 plus.mode 不支持仅凭 accessToken 执行，请改用浏览器模式重试",
        )
    return activate_plus_via_api_with_access_token(access_token, use_cache=use_cache)


def run_plus_binding_with_browser_session(driver, use_cache: bool = True) -> PlusActivationResult:
    """
    按当前配置执行 Plus 绑定浏览器流程。

    参数:
        driver: Selenium WebDriver
    返回:
        PlusActivationResult: 绑定结果
        AI by zb
    """
    mode = get_plus_binding_mode()
    if mode == PLUS_MODE_LEGACY_BROWSER:
        return bind_plus_with_legacy_browser(driver)
    return activate_plus_via_api_with_browser_session(driver, use_cache=use_cache)
