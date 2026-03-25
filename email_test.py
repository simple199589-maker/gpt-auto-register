"""
邮箱服务测试脚本

用法示例:
    uv run python email_test.py create
    uv run python email_test.py fetch --token "mailbox::abc@example.com"
    uv run python email_test.py fetch --token "mailbox::abc@example.com" --since-marker 1742895300456
"""

import argparse
import json
import time
from typing import Any, Dict, Optional

from config import EMAIL_POLL_INTERVAL, EMAIL_WAIT_TIMEOUT
from email_service import (
    create_mailbox_marker,
    create_temp_email,
    fetch_emails,
    fetch_valid_emails
)
from utils import extract_verification_code

MAILBOX_CONTEXT_PREFIX = "mailbox::"


# /**
#  * 解析命令行参数。
#  * @returns {argparse.Namespace} 解析后的参数对象
#  * @author AI by zb
#  */
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="邮箱服务测试脚本")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="创建一个新的临时邮箱并等待验证码")
    create_parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="等待验证码的超时时间（秒），不传则使用配置值"
    )

    fetch_parser = subparsers.add_parser("fetch", help="拉取指定邮箱的有效邮件")
    fetch_parser.add_argument("--token", help="create 返回的兼容令牌")
    fetch_parser.add_argument("--email", help="直接传邮箱地址，脚本会自动转换为兼容令牌")
    fetch_parser.add_argument(
        "--since-marker",
        type=int,
        default=None,
        help="上次保存的时间标记，低于该时间线的邮件会被过滤"
    )
    fetch_parser.add_argument(
        "--without-detail",
        action="store_true",
        help="仅拉取邮件列表，不再补拉详情"
    )

    return parser.parse_args()


# /**
#  * 根据邮箱或兼容令牌构建请求上下文。
#  * @param {Optional[str]} token - 兼容令牌
#  * @param {Optional[str]} email - 邮箱地址
#  * @returns {Optional[str]} 可用于邮箱模块的上下文字符串
#  * @author AI by zb
#  */
def build_mailbox_context(token: Optional[str], email: Optional[str]) -> Optional[str]:
    if token:
        return token.strip()

    if email:
        return f"{MAILBOX_CONTEXT_PREFIX}{email.strip()}"

    return None


# /**
#  * 从上下文中解析邮箱地址。
#  * @param {str} mailbox_context - 兼容令牌或邮箱地址
#  * @returns {str} 邮箱地址
#  * @author AI by zb
#  */
def extract_mailbox(mailbox_context: str) -> str:
    mailbox = mailbox_context.strip()
    if mailbox.startswith(MAILBOX_CONTEXT_PREFIX):
        mailbox = mailbox[len(MAILBOX_CONTEXT_PREFIX):]
    return mailbox


# /**
#  * 执行创建邮箱命令。
#  * @returns {Dict[str, Any]} 创建结果
#  * @author AI by zb
#  */
def handle_create(args: argparse.Namespace) -> Dict[str, Any]:
    email, token = create_temp_email()
    if not email or not token:
        return {
            "success": False,
            "email": email,
            "token": token,
            "verification_start_marker": None,
            "verification_code": None,
            "captured_codes": [],
        }

    verification_start_marker = create_mailbox_marker()
    print(f"📮 测试邮箱已创建: {email}")
    print("⏳ 已进入验证码等待状态，请在业务侧触发发送验证码...")
    wait_result = wait_for_any_verification_email(
        token=token,
        since_marker=verification_start_marker,
        timeout=args.timeout
    )

    return {
        "success": wait_result.get("success", False),
        "email": email,
        "token": token,
        "verification_start_marker": verification_start_marker,
        "verification_code": wait_result.get("verification_code"),
        "captured_codes": wait_result.get("captured_codes", []),
        "rounds": wait_result.get("rounds"),
        "stopped_by_user": wait_result.get("stopped_by_user", False),
    }


# /**
#  * 从邮件结果中提取任意验证码。
#  * @param {Dict[str, Any]} email_item - 单封邮件结果
#  * @returns {Optional[str]} 提取到的验证码
#  * @author AI by zb
#  */
def extract_code_from_email_item(email_item: Dict[str, Any]) -> Optional[str]:
    direct_code = email_item.get("verification_code")
    if direct_code:
        return str(direct_code)

    candidates = [
        email_item.get("subject"),
        email_item.get("body"),
        email_item.get("content"),
        email_item.get("text"),
        email_item.get("html_content"),
        email_item.get("html"),
        email_item.get("preview"),
    ]

    detail = email_item.get("detail") or {}
    candidates.extend([
        detail.get("subject"),
        detail.get("body"),
        detail.get("content"),
        detail.get("text"),
        detail.get("html_content"),
        detail.get("html"),
    ])

    for candidate in candidates:
        code = extract_verification_code(str(candidate or ""))
        if code:
            return code

    return None


# /**
#  * 将邮件对象压缩为便于阅读的摘要。
#  * @param {Dict[str, Any]} email_item - 单封邮件结果
#  * @returns {Dict[str, Any]} 摘要结果
#  * @author AI by zb
#  */
def build_email_summary(email_item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": email_item.get("id"),
        "received_at": email_item.get("received_at") or email_item.get("created_at"),
        "received_marker": email_item.get("received_marker"),
        "sender": email_item.get("sender") or email_item.get("from") or email_item.get("source"),
        "subject": email_item.get("subject"),
        "verification_code": email_item.get("verification_code"),
    }


# /**
#  * 打印单轮轮询摘要。
#  * @param {int} round_index - 当前轮询序号
#  * @param {Any} raw_emails - 原始邮件列表
#  * @param {Dict[str, Any]} result - 过滤后的结果
#  * @param {list} new_emails - 本轮首次看到的有效邮件
#  * @author AI by zb
#  */
def print_poll_snapshot(
    round_index: int,
    raw_emails: Any,
    result: Dict[str, Any],
    new_emails: list
) -> None:
    raw_emails = raw_emails or []
    valid_emails = result.get("emails", []) if isinstance(result, dict) else []
    print(f"\n===== 第 {round_index} 次轮询 =====")
    print(
        "原始数={raw_count} | 有效数={valid_count} | 新邮件数={new_count} | "
        "跳过旧邮件={skipped_old} | 缺少时间={skipped_time} | next_marker={next_marker}".format(
            raw_count=len(raw_emails),
            valid_count=result.get("valid_count", 0),
            new_count=len(new_emails),
            skipped_old=result.get("skipped_before_marker", 0),
            skipped_time=result.get("skipped_without_timestamp", 0),
            next_marker=result.get("next_marker"),
        )
    )

    if raw_emails:
        print("原始邮件摘要:")
        for item in raw_emails:
            print(json.dumps(build_email_summary(item), ensure_ascii=False))
    else:
        print("原始邮件摘要: []")

    if valid_emails:
        print("有效邮件摘要:")
        for item in valid_emails:
            print(json.dumps(build_email_summary(item), ensure_ascii=False))
    else:
        print("有效邮件摘要: []")


# /**
#  * 询问用户是否继续监听后续邮件。
#  * @returns {bool} 是否继续监听
#  * @author AI by zb
#  */
def prompt_continue_listening() -> bool:
    try:
        answer = input("已获取验证码，是否继续监听后续邮件？[y/N]: ").strip().lower()
    except EOFError:
        return False

    return answer in {"y", "yes", "继续", "c", "1"}


# /**
#  * 等待任意验证码邮件，并打印每次轮询摘要。
#  * @param {str} token - 邮箱上下文令牌
#  * @param {int} since_marker - 起始时间标记
#  * @param {Optional[int]} timeout - 超时时间（秒）
#  * @returns {Dict[str, Any]} 等待结果
#  * @author AI by zb
#  */
def wait_for_any_verification_email(
    token: str,
    since_marker: int,
    timeout: Optional[int] = None
) -> Dict[str, Any]:
    effective_timeout = timeout if timeout is not None else EMAIL_WAIT_TIMEOUT
    start_time = time.time()
    round_index = 0
    seen_email_keys = set()
    collected_codes = []
    last_code = None

    while time.time() - start_time < effective_timeout:
        round_index += 1
        raw_emails = fetch_emails(token)
        result = fetch_valid_emails(
            jwt_token=token,
            since_marker=since_marker,
            with_detail=True
        )
        valid_emails = result.get("emails", []) if isinstance(result, dict) else []
        new_emails = []
        for email_item in valid_emails:
            email_key = str(
                email_item.get("id")
                or f"{email_item.get('received_marker')}-{email_item.get('subject')}-{email_item.get('sender')}"
            )
            if email_key in seen_email_keys:
                continue
            seen_email_keys.add(email_key)
            new_emails.append(email_item)

        print_poll_snapshot(round_index, raw_emails, result, new_emails)

        found_codes_in_round = []
        if result.get("success"):
            for email_item in new_emails:
                code = extract_code_from_email_item(email_item)
                if code:
                    if code not in collected_codes:
                        collected_codes.append(code)
                    last_code = code
                    print(f"✅ 当前轮询提取到验证码: {code}")
                    found_codes_in_round.append(code)

        if found_codes_in_round:
            if not prompt_continue_listening():
                return {
                    "success": True,
                    "verification_code": last_code,
                    "captured_codes": collected_codes,
                    "rounds": round_index,
                    "stopped_by_user": True,
                }
            print("🔁 继续监听后续邮件...")
            time.sleep(EMAIL_POLL_INTERVAL)
            continue

        elapsed = int(time.time() - start_time)
        print(f"⏳ 未提取到验证码，{EMAIL_POLL_INTERVAL} 秒后继续轮询，已等待 {elapsed} 秒")
        time.sleep(EMAIL_POLL_INTERVAL)

    print("⏰ 等待验证码超时")
    return {
        "success": bool(last_code),
        "verification_code": last_code,
        "captured_codes": collected_codes,
        "rounds": round_index,
        "stopped_by_user": False,
    }


# /**
#  * 执行拉取邮件命令。
#  * @param {argparse.Namespace} args - 命令行参数
#  * @returns {Dict[str, Any]} 拉取结果
#  * @author AI by zb
#  */
def handle_fetch(args: argparse.Namespace) -> Dict[str, Any]:
    mailbox_context = build_mailbox_context(args.token, args.email)
    if not mailbox_context:
        return {
            "success": False,
            "error": "fetch 命令必须传 --token 或 --email"
        }

    return fetch_valid_emails(
        jwt_token=mailbox_context,
        since_marker=args.since_marker,
        with_detail=not args.without_detail
    )


# /**
#  * 程序入口。
#  * @returns {int} 进程退出码
#  * @author AI by zb
#  */
def main() -> int:
    args = parse_args()

    if args.command == "create":
        result = handle_create(args)
    else:
        result = handle_fetch(args)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
