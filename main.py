#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主流程兼容入口。
AI by zb
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.register import *  # noqa: F401,F403


if __name__ == "__main__":
    run_batch()
