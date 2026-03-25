#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
codex_login_tool.py
===================
Sub2API Admin API 调试工具。AI by zb
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import sys
import uuid
from typing import Any, Dict, Optional

import requests
import yaml


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_BASE_DIR, "config.yaml")


@dataclass
class AdminApiConfig:
    """Sub2API Admin API 配置。AI by zb"""

    base_url: str
    api_key: str


class Sub2ApiAdminClient:
    """Sub2API Admin API 客户端。AI by zb"""

    def __init__(self, config: AdminApiConfig, timeout: int = 30):
        """
        初始化 Admin API 客户端。

        参数:
            config: Admin API 配置
            timeout: HTTP 超时时间（秒）
        返回:
            None
            AI by zb
        """
        self.base_url = str(config.base_url or "").rstrip("/")
        self.api_key = str(config.api_key or "").strip()
        self.timeout = int(timeout)
        self.session = requests.Session()

    def _build_headers(self, idempotency_key: str = "") -> Dict[str, str]:
        """
        构建请求头。

        参数:
            idempotency_key: 幂等键
        返回:
            dict: 请求头字典
            AI by zb
        """
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        if str(idempotency_key or "").strip():
            headers["Idempotency-Key"] = str(idempotency_key).strip()
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """
        发起 Admin API 请求并返回统一结果。

        参数:
            method: HTTP 方法
            path: 接口路径
            payload: JSON 请求体
            idempotency_key: 幂等键
        返回:
            dict: 统一响应结果
            AI by zb
        """
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method=method,
            url=url,
            headers=self._build_headers(idempotency_key),
            json=payload,
            timeout=self.timeout,
        )

        try:
            data = response.json()
        except Exception:
            data = {"raw_text": response.text}

        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "url": url,
            "method": method.upper(),
            "data": data,
        }

    def get_user(self, user_id: int) -> Dict[str, Any]:
        """
        查询指定用户信息。

        参数:
            user_id: 用户 ID
        返回:
            dict: 接口响应
            AI by zb
        """
        return self._request("GET", f"/api/v1/admin/users/{int(user_id)}")

    def create_and_redeem(
        self,
        *,
        code: str,
        value: float,
        user_id: int,
        notes: str,
        idempotency_key: str = "",
        redeem_type: str = "balance",
    ) -> Dict[str, Any]:
        """
        一步完成创建兑换码并兑换给用户。

        参数:
            code: 兑换码
            value: 金额
            user_id: 用户 ID
            notes: 备注
            idempotency_key: 幂等键
            redeem_type: 兑换类型，默认 balance
        返回:
            dict: 接口响应
            AI by zb
        """
        effective_key = str(idempotency_key or "").strip() or f"pay-{code}-success"
        payload = {
            "code": code,
            "type": redeem_type,
            "value": float(value),
            "user_id": int(user_id),
            "notes": notes,
        }
        return self._request(
            "POST",
            "/api/v1/admin/redeem-codes/create-and-redeem",
            payload=payload,
            idempotency_key=effective_key,
        )

    def adjust_balance(
        self,
        *,
        user_id: int,
        balance: float,
        operation: str,
        notes: str,
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """
        调整用户余额。

        参数:
            user_id: 用户 ID
            balance: 调整金额
            operation: set/add/subtract
            notes: 备注
            idempotency_key: 幂等键
        返回:
            dict: 接口响应
            AI by zb
        """
        effective_key = str(idempotency_key or "").strip() or (
            f"balance-{operation}-{user_id}-{uuid.uuid4().hex[:12]}"
        )
        payload = {
            "balance": float(balance),
            "operation": operation,
            "notes": notes,
        }
        return self._request(
            "POST",
            f"/api/v1/admin/users/{int(user_id)}/balance",
            payload=payload,
            idempotency_key=effective_key,
        )


def load_yaml_config(config_path: str = _CONFIG_FILE) -> Dict[str, Any]:
    """
    读取 YAML 配置。

    参数:
        config_path: 配置文件路径
    返回:
        dict: 配置字典
        AI by zb
    """
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data if isinstance(data, dict) else {}


def resolve_admin_api_config(base_url: str, api_key: str) -> AdminApiConfig:
    """
    解析最终的 Admin API 配置。

    参数:
        base_url: 命令行传入的 base_url
        api_key: 命令行传入的 api_key
    返回:
        AdminApiConfig: 解析后的配置
        AI by zb
    """
    config = load_yaml_config()
    sub2api_config = config.get("sub2api") or {}
    effective_base_url = str(base_url or sub2api_config.get("base_url") or "").strip()
    effective_api_key = str(api_key or sub2api_config.get("api_key") or "").strip()

    if not effective_base_url:
        raise ValueError("缺少 Sub2API base_url，请在 config.yaml.sub2api.base_url 或命令行传入")
    if not effective_api_key:
        raise ValueError("缺少 Sub2API api_key，请在 config.yaml.sub2api.api_key 或命令行传入")

    return AdminApiConfig(base_url=effective_base_url, api_key=effective_api_key)


def add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    """
    为子命令补充共享参数。

    参数:
        parser: 子命令解析器
    返回:
        None
            AI by zb
    """
    parser.add_argument("--base-url", default="", help="Sub2API 服务地址，默认读取 config.yaml")
    parser.add_argument("--api-key", default="", help="Sub2API Admin API Key，默认读取 config.yaml")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP 超时时间（秒）")


def build_arg_parser() -> argparse.ArgumentParser:
    """
    构造命令行参数解析器。

    返回:
        argparse.ArgumentParser: 参数解析器
        AI by zb
    """
    parser = argparse.ArgumentParser(description="Sub2API Admin API 调试工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_user_parser = subparsers.add_parser("get-user", help="查询用户信息")
    add_shared_arguments(get_user_parser)
    get_user_parser.add_argument("--user-id", type=int, required=True, help="用户 ID")

    create_redeem_parser = subparsers.add_parser("create-and-redeem", help="创建兑换码并直接兑换")
    add_shared_arguments(create_redeem_parser)
    create_redeem_parser.add_argument("--user-id", type=int, required=True, help="用户 ID")
    create_redeem_parser.add_argument("--code", required=True, help="兑换码")
    create_redeem_parser.add_argument("--value", type=float, required=True, help="金额")
    create_redeem_parser.add_argument("--notes", default="", help="备注")
    create_redeem_parser.add_argument("--type", default="balance", help="兑换类型，默认 balance")
    create_redeem_parser.add_argument("--idempotency-key", default="", help="幂等键")

    balance_parser = subparsers.add_parser("adjust-balance", help="调整用户余额")
    add_shared_arguments(balance_parser)
    balance_parser.add_argument("--user-id", type=int, required=True, help="用户 ID")
    balance_parser.add_argument("--balance", type=float, required=True, help="调整金额")
    balance_parser.add_argument(
        "--operation",
        choices=["set", "add", "subtract"],
        required=True,
        help="调整方式"
    )
    balance_parser.add_argument("--notes", default="", help="备注")
    balance_parser.add_argument("--idempotency-key", default="", help="幂等键")

    return parser


def execute_command(args: argparse.Namespace) -> Dict[str, Any]:
    """
    执行指定命令。

    参数:
        args: 解析后的命令行参数
    返回:
        dict: 接口调用结果
        AI by zb
    """
    admin_config = resolve_admin_api_config(args.base_url, args.api_key)
    client = Sub2ApiAdminClient(admin_config, timeout=args.timeout)

    if args.command == "get-user":
        return client.get_user(args.user_id)

    if args.command == "create-and-redeem":
        notes = str(args.notes or "").strip() or f"manual redeem for user {args.user_id}"
        return client.create_and_redeem(
            code=str(args.code).strip(),
            value=float(args.value),
            user_id=int(args.user_id),
            notes=notes,
            idempotency_key=str(args.idempotency_key or "").strip(),
            redeem_type=str(args.type or "balance").strip(),
        )

    if args.command == "adjust-balance":
        notes = str(args.notes or "").strip() or "manual correction"
        return client.adjust_balance(
            user_id=int(args.user_id),
            balance=float(args.balance),
            operation=str(args.operation).strip(),
            notes=notes,
            idempotency_key=str(args.idempotency_key or "").strip(),
        )

    raise ValueError(f"不支持的命令: {args.command}")


def main() -> int:
    """
    命令行入口。

    返回:
        int: 进程退出码
        AI by zb
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        result = execute_command(args)
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
