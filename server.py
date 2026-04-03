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
    startup_options = parse_server_startup_options(default_port=5005)
    start_web_server(
        port=int(startup_options.port),
        activation_api_index=startup_options.activation_api_index,
    )
