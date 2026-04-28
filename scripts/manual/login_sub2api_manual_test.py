#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
登录到 Sub2Api 手工验证脚本。
AI by zb
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.login_sub2api import import_login_account, login_and_upload_account, upload_existing_tokens_to_sub2api


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    返回:
        argparse.Namespace: 参数对象
        AI by zb
    """
    parser = argparse.ArgumentParser(description="登录到 Sub2Api 手工验证脚本")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="导入账号密码")
    import_parser.add_argument("--email", required=True, help="账号邮箱")
    import_parser.add_argument("--password", required=True, help="账号密码")
    import_parser.add_argument("--mailbox-context", default="", help="邮箱接码上下文")

    login_parser = subparsers.add_parser("login", help="登录验证并上传")
    login_parser.add_argument("--email", required=True, help="账号邮箱")
    login_parser.add_argument("--otp-mode", choices=["auto", "manual"], default="auto", help="OTP 模式")
    login_parser.add_argument("--skip-upload", action="store_true", help="只登录保存，不上传 Sub2Api")

    upload_parser = subparsers.add_parser("upload", help="仅上传已有 OAuth 三件套")
    upload_parser.add_argument("--email", required=True, help="账号邮箱")

    return parser.parse_args()


def main() -> int:
    """
    执行手工验证命令。

    返回:
        int: 退出码
        AI by zb
    """
    args = parse_args()
    if args.command == "import":
        result = import_login_account(
            email=str(args.email),
            password=str(args.password),
            mailbox_context=str(args.mailbox_context or ""),
        )
        print(json.dumps({"success": True, "account": result}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "upload":
        result = upload_existing_tokens_to_sub2api(str(args.email))
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.success else 1

    result = login_and_upload_account(
        email=str(args.email),
        otp_mode=str(args.otp_mode or "auto"),
        skip_upload=bool(args.skip_upload),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
