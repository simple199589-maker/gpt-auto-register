#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex 登录工具入口。
AI by zb
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.codex.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
