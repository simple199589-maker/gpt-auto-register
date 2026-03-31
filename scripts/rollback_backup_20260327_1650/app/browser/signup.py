"""注册与登录流程能力。AI by zb"""

from ._legacy import (
    CHATGPT_HOME_URLS,
    CHATGPT_LOGIN_URLS,
    attach_monitor_callback,
    click_resend_verification_email,
    detach_monitor_callback,
    emit_monitor_event,
    enter_verification_code,
    fill_profile_info,
    fill_signup_form,
    login,
    open_first_reachable_url,
)

__all__ = [
    "CHATGPT_HOME_URLS",
    "CHATGPT_LOGIN_URLS",
    "attach_monitor_callback",
    "click_resend_verification_email",
    "detach_monitor_callback",
    "emit_monitor_event",
    "enter_verification_code",
    "fill_profile_info",
    "fill_signup_form",
    "login",
    "open_first_reachable_url",
]
