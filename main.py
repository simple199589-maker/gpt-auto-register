#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量登录上传兼容入口。
AI by zb
"""

from __future__ import annotations

import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.config import cfg
from app.login_sub2api import run_batch_login_sub2api


def main() -> int:
    """
    执行配置数量内的批量登录上传任务。

    返回:
        int: 退出码
        AI by zb
    """
    summary = run_batch_login_sub2api(count=int(cfg.registration.total_accounts or 1))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if int(summary.get("fail") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
