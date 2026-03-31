"""浏览器自动化包。AI by zb"""

from .common import (
    check_and_handle_error,
    click_button_with_retry,
    handle_stripe_input,
    type_slowly,
)
from .driver import SafeChrome, create_driver, get_local_chrome_major_version
from .signup import (
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
from .subscription import cancel_subscription, subscribe_plus_trial

__all__ = [
    "SafeChrome",
    "CHATGPT_HOME_URLS",
    "CHATGPT_LOGIN_URLS",
    "attach_monitor_callback",
    "cancel_subscription",
    "check_and_handle_error",
    "click_button_with_retry",
    "click_resend_verification_email",
    "create_driver",
    "detach_monitor_callback",
    "enter_verification_code",
    "emit_monitor_event",
    "fill_profile_info",
    "fill_signup_form",
    "get_local_chrome_major_version",
    "handle_stripe_input",
    "login",
    "open_first_reachable_url",
    "subscribe_plus_trial",
    "type_slowly",
]
