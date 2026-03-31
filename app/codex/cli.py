#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex 登录命令行入口。
AI by zb
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from app.codex.runtime import get_logger, run_codex_login


def build_arg_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器。

    返回:
        argparse.ArgumentParser: 参数解析器
        AI by zb
    """
    parser = argparse.ArgumentParser(description="Codex 账密直登并上传到 Sub2Api")
    parser.add_argument("--email", required=True, help="登录邮箱")
    parser.add_argument("--password", required=True, help="登录密码")
    parser.add_argument("--config", default="", help="配置文件路径，默认读取根目录 config.yaml")
    parser.add_argument("--proxy", default="", help="代理地址，默认读取 config.yaml.proxy")
    parser.add_argument(
        "--otp-mode",
        choices=["auto", "manual"],
        default="auto",
        help="邮箱验证码模式，默认 auto",
    )
    parser.add_argument("--output-dir", default="", help="token 文件输出目录")
    parser.add_argument("--skip-upload", action="store_true", help="只登录并保存，不上传到 Sub2Api")
    parser.add_argument("--skip-save", action="store_true", help="只登录并上传，不落本地文件")
    return parser


def execute_command(args: argparse.Namespace) -> Dict[str, Any]:
    """
    执行登录命令。

    参数:
        args: 解析后的命令行参数
    返回:
        Dict[str, Any]: 结果字典
        AI by zb
    """
    logger = get_logger()
    result = run_codex_login(
        email=str(args.email).strip(),
        password=str(args.password),
        config_path=str(args.config or "").strip(),
        proxy=str(args.proxy or "").strip(),
        otp_mode=str(args.otp_mode or "auto").strip(),
        upload=not bool(args.skip_upload),
        save_local=not bool(args.skip_save),
        output_dir=str(args.output_dir or "").strip(),
        logger=logger,
    )
    return result.to_dict()


def main() -> int:
    """
    命令行主入口。

    返回:
        int: 进程退出码
        AI by zb
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        result = execute_command(args)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1
