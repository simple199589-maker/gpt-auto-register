"""浏览器公共辅助能力。AI by zb"""

from ._legacy import (
    check_and_handle_error,
    click_button_with_retry,
    handle_stripe_input,
    type_slowly,
)

__all__ = [
    "check_and_handle_error",
    "click_button_with_retry",
    "handle_stripe_input",
    "type_slowly",
]
