"""Codex OTP 处理能力。AI by zb"""

from ._runtime_impl import create_mailbox_marker, prompt_for_email_otp, resolve_mailbox_context

__all__ = [
    "create_mailbox_marker",
    "prompt_for_email_otp",
    "resolve_mailbox_context",
]
