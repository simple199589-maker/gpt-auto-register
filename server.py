#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 服务兼容入口。
AI by zb
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.web_server import *  # noqa: F401,F403


if __name__ == "__main__":
    from waitress import serve

    print("🌐 Web Server started at http://localhost:5000")
    serve(app, host="0.0.0.0", port=5000, threads=6)
