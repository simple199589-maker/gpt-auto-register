#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动 OTP 的 Codex 登录示例。
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

from app.codex.runtime import run_codex_login


TEST_EMAIL = "ivy.gonzalez@joini.cloud"
TEST_PASSWORD = "$%4Y8DUmDYsQ5Rpq"


def parse_args() -> argparse.Namespace:
    """
    解析手工登录脚本参数。

    返回:
        argparse.Namespace: 解析后的参数对象
        AI by zb
    """
    parser = argparse.ArgumentParser(description="Codex 手工 OTP 登录脚本")
    parser.add_argument("--email", default=TEST_EMAIL, help="登录邮箱")
    parser.add_argument("--password", default=TEST_PASSWORD, help="登录密码")
    parser.add_argument("--config", default="", help="配置文件路径")
    parser.add_argument("--proxy", default="", help="代理地址")
    parser.add_argument("--output-dir", default="", help="token 输出目录")
    parser.add_argument("--skip-upload", action="store_true", help="不上传到 Sub2Api")
    parser.add_argument("--skip-save", action="store_true", help="不保存本地 token")
    return parser.parse_args()


def main() -> int:
    """
    运行手动 OTP 示例。

    返回:
        int: 进程退出码
        AI by zb
    """
    args = parse_args()
    result = run_codex_login(
        email=str(args.email),
        password=str(args.password),
        config_path=str(args.config or ""),
        proxy=str(args.proxy or ""),
        otp_mode="manual",
        upload=not bool(args.skip_upload),
        save_local=not bool(args.skip_save),
        output_dir=str(args.output_dir or ""),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
