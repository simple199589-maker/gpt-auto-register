#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex 登录运行时能力。
AI by zb
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import logging
import random
import re
import secrets
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

import requests
import urllib3
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.codex.sub2api import Sub2ApiConfig, Sub2ApiUploader, normalize_group_ids
from app.proxy import proxy_config_to_url


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_FILE = ROOT_DIR / "config.yaml"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output_tokens"
_LOGIN_FAILURE_CONTEXT = threading.local()

OPENAI_AUTH_BASE = "https://auth.openai.com"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OAUTH_SCOPE = "openid profile email offline_access"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"'

COMMON_HEADERS: Dict[str, str] = {
    "accept": "application/json",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json",
    "origin": OPENAI_AUTH_BASE,
    "user-agent": USER_AGENT,
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

AUTH_JSON_HEADERS: Dict[str, str] = {
    "accept": "application/json",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json",
    "priority": "u=1, i",
    "user-agent": USER_AGENT,
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-mobile": COMMON_HEADERS["sec-ch-ua-mobile"],
    "sec-ch-ua-platform": COMMON_HEADERS["sec-ch-ua-platform"],
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

NAVIGATE_HEADERS: Dict[str, str] = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "zh-CN,zh;q=0.9",
    "user-agent": USER_AGENT,
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


@dataclass
class CodexRunResult:
    """Codex 登录执行结果。AI by zb"""

    success: bool
    email: str
    uploaded: bool = False
    output_file: str = ""
    error: str = ""
    tokens: Optional[Dict[str, Any]] = None
    token_payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        将结果转成字典。

        返回:
            Dict[str, Any]: 序列化结果
            AI by zb
        """
        return asdict(self)


def get_logger(name: str = "codex-login") -> logging.Logger:
    """
    获取运行时日志器。

    参数:
        name: 日志器名称
    返回:
        logging.Logger: 日志器对象
        AI by zb
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def set_last_login_failure_reason(reason: str) -> None:
    """
    保存当前线程最近一次 Codex 登录失败原因。

    参数:
        reason: 失败原因
    返回:
        None
        AI by zb
    """
    _LOGIN_FAILURE_CONTEXT.reason = str(reason or "").strip()


def get_last_login_failure_reason(clear: bool = False) -> str:
    """
    获取当前线程最近一次 Codex 登录失败原因。

    参数:
        clear: 是否读取后清空
    返回:
        str: 失败原因
        AI by zb
    """
    reason = str(getattr(_LOGIN_FAILURE_CONTEXT, "reason", "") or "").strip()
    if clear:
        set_last_login_failure_reason("")
    return reason


def fail_oauth_login(reason: str, logger: logging.Logger, email: str) -> Optional[Dict[str, Any]]:
    """
    记录 OAuth 登录失败原因并返回空结果。

    参数:
        reason: 失败原因
        logger: 日志器
        email: 登录邮箱
    返回:
        None
        AI by zb
    """
    message = str(reason or "Codex OAuth 登录失败").strip()
    set_last_login_failure_reason(message)
    logger.warning("[Codex] %s | email=%s", message, email)
    return None


def load_runtime_config(config_path: str = "") -> Dict[str, Any]:
    """
    读取运行配置。

    参数:
        config_path: 指定配置文件
    返回:
        Dict[str, Any]: YAML 配置字典
        AI by zb
    """
    target_path = Path(config_path).resolve() if config_path else DEFAULT_CONFIG_FILE
    if not target_path.exists():
        return {}
    with open(target_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data if isinstance(data, dict) else {}


def resolve_email_wait_timeout(config: Optional[Dict[str, Any]] = None, default: int = 60) -> int:
    """
    从运行配置中解析邮箱验证码等待秒数。

    参数:
        config: 运行配置字典
        default: 默认等待秒数
    返回:
        int: 等待秒数
        AI by zb
    """
    raw_value: Any = default
    if isinstance(config, dict):
        email_config = config.get("email") or {}
        if isinstance(email_config, dict):
            raw_value = email_config.get("wait_timeout", raw_value)
    try:
        return max(int(raw_value or default), 1)
    except (TypeError, ValueError):
        return max(int(default or 60), 1)


def resolve_proxy(config: Dict[str, Any], override_proxy: str = "") -> str:
    """
    解析最终代理地址。

    参数:
        config: 运行配置
        override_proxy: 命令行传入的代理
    返回:
        str: 代理地址
        AI by zb
    """
    if str(override_proxy or "").strip():
        return str(override_proxy).strip()
    return proxy_config_to_url(config.get("proxy") or {})


def create_session(proxy: str = "") -> requests.Session:
    """
    创建带重试的 requests.Session。

    参数:
        proxy: HTTP/HTTPS 代理
    返回:
        requests.Session: 会话对象
        AI by zb
    """
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


def generate_pkce() -> Tuple[str, str]:
    """
    生成 PKCE 参数。

    返回:
        Tuple[str, str]: code_verifier 与 code_challenge
        AI by zb
    """
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def generate_datadog_trace() -> Dict[str, str]:
    """
    构建 Datadog 追踪头。

    返回:
        Dict[str, str]: 追踪头集合
        AI by zb
    """
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    trace_hex = format(int(trace_id), "016x")
    parent_hex = format(int(parent_id), "016x")
    return {
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    }


def build_auth_json_headers(
    referer: str,
    device_id: str = "",
    include_datadog: bool = True,
    include_device_id: bool = True,
) -> Dict[str, str]:
    """
    构建认证接口请求头。

    参数:
        referer: Referer 地址
        device_id: 设备 ID
        include_datadog: 是否带上 Datadog 头
        include_device_id: 是否带上设备 ID
    返回:
        Dict[str, str]: 请求头
        AI by zb
    """
    headers = dict(AUTH_JSON_HEADERS)
    headers["origin"] = OPENAI_AUTH_BASE
    headers["referer"] = referer
    if include_device_id and device_id:
        headers["oai-device-id"] = device_id
    if include_datadog:
        headers.update(generate_datadog_trace())
    return headers


class SentinelTokenGenerator:
    """Sentinel token 生成器。AI by zb"""

    MAX_ATTEMPTS = 500_000

    def __init__(self, device_id: Optional[str] = None) -> None:
        """
        初始化 token 生成器。

        参数:
            device_id: 设备 ID
        返回:
            None
            AI by zb
        """
        self.device_id = device_id or str(uuid.uuid4())
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str) -> str:
        """
        计算 FNV1A 32 位哈希。

        参数:
            text: 待计算文本
        返回:
            str: 哈希结果
            AI by zb
        """
        value = 2166136261
        for char in text:
            value ^= ord(char)
            value = (value * 16777619) & 0xFFFFFFFF
        value ^= value >> 16
        value = (value * 2246822507) & 0xFFFFFFFF
        value ^= value >> 13
        value = (value * 3266489909) & 0xFFFFFFFF
        value ^= value >> 16
        return format(value & 0xFFFFFFFF, "08x")

    @staticmethod
    def _b64(data: Any) -> str:
        """
        对 JSON 数据执行 Base64 编码。

        参数:
            data: 任意 JSON 可序列化对象
        返回:
            str: Base64 字符串
            AI by zb
        """
        content = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return base64.b64encode(content.encode("utf-8")).decode("ascii")

    def _get_config(self) -> List[Any]:
        """
        生成 Sentinel 配置快照。

        返回:
            List[Any]: Sentinel 参数
            AI by zb
        """
        now = dt.datetime.now(dt.timezone.utc).strftime(
            "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)"
        )
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        return [
            "1920x1080",
            now,
            4294705152,
            random.random(),
            USER_AGENT,
            "https://sentinel.openai.com/sentinel/20260219f9f6/sdk.js",
            None,
            None,
            "zh-CN",
            "zh-CN,zh",
            random.random(),
            "vendorSub−undefined",
            "location",
            "Object",
            perf_now,
            self.sid,
            "",
            random.choice([4, 8, 12, 16]),
            time_origin,
        ]

    def generate_requirements_token(self) -> str:
        """
        生成 requirements token。

        返回:
            str: requirements token
            AI by zb
        """
        config = self._get_config()
        config[3] = 1
        config[9] = round(random.uniform(5, 50))
        return "gAAAAAC" + self._b64(config)

    def generate_token(self, seed: Optional[str] = None, difficulty: Optional[str] = None) -> str:
        """
        生成最终 Sentinel token。

        参数:
            seed: 服务端挑战 seed
            difficulty: 难度阈值
        返回:
            str: Sentinel token
            AI by zb
        """
        actual_seed = seed or self.requirements_seed
        actual_difficulty = difficulty or "0"
        config = self._get_config()
        start_time = time.time()
        for attempt in range(self.MAX_ATTEMPTS):
            config[3] = attempt
            config[9] = round((time.time() - start_time) * 1000)
            data = self._b64(config)
            hash_hex = self._fnv1a_32(actual_seed + data)
            if hash_hex[: len(actual_difficulty)] <= actual_difficulty:
                return "gAAAAAB" + data + "~S"
        return "gAAAAAB" + self._b64(str(None))


def fetch_sentinel_challenge(
    session: requests.Session,
    device_id: str,
    flow: str = "authorize_continue",
) -> Optional[Dict[str, Any]]:
    """
    获取 Sentinel challenge。

    参数:
        session: HTTP 会话
        device_id: 设备 ID
        flow: Sentinel flow 名称
    返回:
        Optional[Dict[str, Any]]: 挑战数据
        AI by zb
    """
    generator = SentinelTokenGenerator(device_id=device_id)
    body = {"p": generator.generate_requirements_token(), "id": device_id, "flow": flow}
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
        "User-Agent": USER_AGENT,
        "Origin": "https://sentinel.openai.com",
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    try:
        response = session.post(
            "https://sentinel.openai.com/backend-api/sentinel/req",
            data=json.dumps(body),
            headers=headers,
            timeout=15,
            verify=False,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def build_sentinel_token(
    session: requests.Session,
    device_id: str,
    flow: str = "authorize_continue",
) -> Optional[str]:
    """
    构建完整 openai-sentinel-token。

    参数:
        session: HTTP 会话
        device_id: 设备 ID
        flow: Sentinel flow 名称
    返回:
        Optional[str]: token 字符串
        AI by zb
    """
    challenge = fetch_sentinel_challenge(session, device_id, flow)
    generator = SentinelTokenGenerator(device_id=device_id)
    if not challenge:
        return json.dumps(
            {
                "p": generator.generate_requirements_token(),
                "t": "",
                "c": "",
                "id": device_id,
                "flow": flow,
            }
        )

    proof = challenge.get("proofofwork", {})
    if isinstance(proof, dict) and proof.get("required") and proof.get("seed"):
        payload = generator.generate_token(
            seed=str(proof.get("seed") or ""),
            difficulty=str(proof.get("difficulty") or "0"),
        )
    else:
        payload = generator.generate_requirements_token()

    return json.dumps(
        {
            "p": payload,
            "t": "",
            "c": challenge.get("token", ""),
            "id": device_id,
            "flow": flow,
        }
    )


def generate_random_name() -> Tuple[str, str]:
    """
    生成随机英文姓名。

    返回:
        Tuple[str, str]: 名和姓
        AI by zb
    """
    first_names = ["James", "Robert", "John", "Michael", "David", "Mary", "Emma", "Olivia"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]
    return random.choice(first_names), random.choice(last_names)


def generate_random_birthday() -> str:
    """
    生成随机生日字符串。

    返回:
        str: YYYY-MM-DD 格式生日
        AI by zb
    """
    year = random.randint(1992, 2003)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    """
    解码 JWT payload。

    参数:
        token: JWT 字符串
    返回:
        Dict[str, Any]: payload 数据
        AI by zb
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_token_dict(email: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
    """
    组装标准 token JSON。

    参数:
        email: 账号邮箱
        tokens: OAuth token 响应
    返回:
        Dict[str, Any]: 标准 token 结构
        AI by zb
    """
    access_token = str(tokens.get("access_token") or "")
    refresh_token = str(tokens.get("refresh_token") or "")
    id_token = str(tokens.get("id_token") or "")

    payload = decode_jwt_payload(access_token)
    auth_info = payload.get("https://api.openai.com/auth", {})
    account_id = auth_info.get("chatgpt_account_id", "") if isinstance(auth_info, dict) else ""

    exp_timestamp = payload.get("exp", 0)
    now = dt.datetime.now(tz=dt.timezone(dt.timedelta(hours=8)))
    expired_str = ""
    if exp_timestamp:
        exp_dt = dt.datetime.fromtimestamp(exp_timestamp, tz=dt.timezone(dt.timedelta(hours=8)))
        expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    return {
        "type": "codex",
        "email": email,
        "expired": expired_str,
        "id_token": id_token,
        "account_id": account_id,
        "access_token": access_token,
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "refresh_token": refresh_token,
    }


def create_mailbox_marker() -> int:
    """
    创建邮箱轮询起始时间标记。

    返回:
        int: 毫秒级时间戳
        AI by zb
    """
    return int(time.time() * 1000)


def create_mailbox_marker_with_skew(skew_seconds: int = 30) -> int:
    return int((time.time() - max(int(skew_seconds or 0), 0)) * 1000)



def prompt_for_email_otp(
    email: str,
    logger: Optional[logging.Logger] = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    提示用户手动输入邮箱验证码。

    参数:
        email: 邮箱地址
        logger: 日志器
        timeout: 等待时长
    返回:
        Optional[str]: 6 位验证码
        AI by zb
    """
    effective_timeout = resolve_email_wait_timeout({"email": {"wait_timeout": timeout}}, default=60)
    deadline = time.time() + effective_timeout
    active_logger = logger or get_logger()

    while time.time() < deadline:
        remain = max(1, int(deadline - time.time()))
        try:
            raw = input(
                f"\n[Codex] 已向 {email} 发送邮箱验证码，请输入 6 位 code "
                f"(剩余 {remain}s，直接回车取消): "
            ).strip()
        except EOFError:
            active_logger.warning("[Codex] 当前环境无法读取手动输入 | email=%s", email)
            return None

        if not raw:
            active_logger.warning("[Codex] 未输入验证码，已取消登录 | email=%s", email)
            return None

        match = re.search(r"(\d{6})", raw)
        if match:
            return match.group(1)

        active_logger.warning("[Codex] 输入内容未识别到 6 位验证码，请重试 | email=%s", email)

    active_logger.warning("[Codex] 等待手动输入 OTP 超时 | email=%s", email)
    return None


def resolve_mailbox_context(email: str, explicit_context: str = "") -> str:
    """
    推断邮箱上下文标识。

    参数:
        email: 邮箱地址
        explicit_context: 显式传入的上下文
    返回:
        str: mailbox context
        AI by zb
    """
    if str(explicit_context or "").strip():
        return str(explicit_context).strip()
    if not str(email or "").strip():
        return ""
    return f"mailbox::{email.strip()}"


def extract_workspace_id(payload: Any) -> Optional[str]:
    """
    从不同结构中提取 workspace_id。

    参数:
        payload: 任意 JSON 结构
    返回:
        Optional[str]: workspace_id
        AI by zb
    """
    if payload is None:
        return None
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if isinstance(payload, list):
        for item in payload:
            found = extract_workspace_id(item)
            if found:
                return found
        return None
    if not isinstance(payload, dict):
        return None

    direct_workspace_id = str(payload.get("workspace_id") or "").strip()
    if direct_workspace_id:
        return direct_workspace_id

    workspaces = payload.get("workspaces")
    if isinstance(workspaces, list):
        preferred = [
            item
            for item in workspaces
            if isinstance(item, dict) and str(item.get("kind") or "").strip() == "organization"
        ]
        fallback = [item for item in workspaces if isinstance(item, dict)]
        for item in preferred + fallback:
            workspace_id = str(item.get("id") or item.get("workspace_id") or "").strip()
            if workspace_id:
                return workspace_id

    workspace = payload.get("workspace")
    if isinstance(workspace, dict):
        workspace_id = str(workspace.get("id") or workspace.get("workspace_id") or "").strip()
        if workspace_id:
            return workspace_id

    for key in ("client_auth_session", "data", "items", "results", "value"):
        nested = payload.get(key)
        found = extract_workspace_id(nested)
        if found:
            return found

    direct_id = str(payload.get("id") or "").strip()
    if direct_id and any(key in payload for key in ("name", "slug", "projects")):
        return direct_id
    return None


def _decode_auth_session_cookie_value(cookie_value: str) -> Optional[Dict[str, Any]]:
    """
    解码单个 auth session cookie。

    参数:
        cookie_value: cookie 内容
    返回:
        Optional[Dict[str, Any]]: 解码后的字典
        AI by zb
    """
    part = cookie_value.split(".")[0] if "." in cookie_value else cookie_value
    padding = 4 - len(part) % 4
    try:
        raw = base64.urlsafe_b64decode(part + ("=" * (padding if padding != 4 else 0)))
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def decode_auth_session_cookie(session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    解析 oai-client-auth-session cookie。

    参数:
        session: HTTP 会话
    返回:
        Optional[Dict[str, Any]]: 解码后的 session 数据
        AI by zb
    """
    fallback_data: Optional[Dict[str, Any]] = None
    for cookie in session.cookies:
        if cookie.name != "oai-client-auth-session":
            continue
        data = _decode_auth_session_cookie_value(cookie.value)
        if isinstance(data, dict):
            if extract_workspace_id(data):
                return data
            if fallback_data is None:
                fallback_data = data
    return fallback_data


def summarize_auth_session_cookies(session: requests.Session) -> List[Dict[str, Any]]:
    """
    汇总 auth session cookie 状态。

    参数:
        session: HTTP 会话
    返回:
        List[Dict[str, Any]]: 汇总结果
        AI by zb
    """
    summaries: List[Dict[str, Any]] = []
    for cookie in session.cookies:
        if cookie.name != "oai-client-auth-session":
            continue
        data = _decode_auth_session_cookie_value(cookie.value) or {}
        workspaces = data.get("workspaces") if isinstance(data, dict) else None
        workspace_items = workspaces if isinstance(workspaces, list) else []
        summaries.append(
            {
                "domain": getattr(cookie, "domain", ""),
                "path": getattr(cookie, "path", ""),
                "session_id": str(data.get("session_id") or ""),
                "original_screen_hint": str(data.get("original_screen_hint") or ""),
                "email_verification_mode": str(data.get("email_verification_mode") or ""),
                "workspace_count": len(workspace_items),
                "workspace_kinds": [
                    str((item or {}).get("kind") or "")
                    for item in workspace_items
                    if isinstance(item, dict)
                ],
                "has_workspace_id": bool(extract_workspace_id(data)),
            }
        )
    return summaries


def ensure_workspace_context(
    session: requests.Session,
    oauth_issuer: str,
    email: str,
    log_prefix: str,
    logger: Optional[logging.Logger] = None,
    max_attempts: int = 3,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    主动访问 workspace 页面并等待 workspace_id。

    参数:
        session: HTTP 会话
        oauth_issuer: OAuth 服务根地址
        email: 当前邮箱
        log_prefix: 日志前缀
        logger: 日志器
        max_attempts: 最大重试次数
    返回:
        Tuple[Optional[Dict[str, Any]], Optional[str]]: session 数据与 workspace_id
        AI by zb
    """
    active_logger = logger or get_logger()
    workspace_url = f"{oauth_issuer}/workspace"
    session_data: Optional[Dict[str, Any]] = None
    workspace_id: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(
                workspace_url,
                headers=NAVIGATE_HEADERS,
                verify=False,
                timeout=20,
                allow_redirects=True,
            )
            active_logger.info(
                "%s workspace 页面加载: HTTP %s | url=%s | attempt=%d | email=%s",
                log_prefix,
                response.status_code,
                str(response.url)[:100],
                attempt,
                email,
            )
        except Exception as exc:
            active_logger.warning("%s workspace 页面加载异常: %s | email=%s", log_prefix, exc, email)

        session_data = decode_auth_session_cookie(session)
        workspace_id = extract_workspace_id(session_data)
        active_logger.info(
            "%s workspace snapshots: %s | email=%s",
            log_prefix,
            summarize_auth_session_cookies(session),
            email,
        )
        if workspace_id:
            return session_data, workspace_id
        if attempt < max_attempts:
            time.sleep(1)

    return session_data, workspace_id


def dump_client_auth_session(
    session: requests.Session,
    oauth_issuer: str,
    referer: str,
    email: str,
    logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    headers = dict(AUTH_JSON_HEADERS)
    headers.pop("content-type", None)
    headers["referer"] = referer
    try:
        response = session.get(
            f"{oauth_issuer}/api/accounts/client_auth_session_dump",
            headers=headers,
            verify=False,
            timeout=20,
        )
        logger.info(
            "[Codex] client_auth_session_dump: HTTP %s | referer=%s | body=%s | email=%s",
            response.status_code,
            referer[:100],
            response.text[:300].replace("\n", " ").replace("\r", " "),
            email,
        )
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("[Codex] client_auth_session_dump 异常: %s | email=%s", exc, email)
    return None


def _extract_code_from_url(url: str) -> Optional[str]:
    """
    从 URL 中提取 OAuth code。

    参数:
        url: URL 字符串
    返回:
        Optional[str]: code 参数
        AI by zb
    """
    if not url or "code=" not in url:
        return None
    try:
        return parse_qs(urlparse(url).query).get("code", [None])[0]
    except Exception:
        return None


def _walk_json_for_state_nonce(obj: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    在任意 JSON 结构里递归查找 state / nonce 字段。

    参数:
        obj: JSON 反序列化后的对象
    返回:
        Tuple[Optional[str], Optional[str]]: (state, nonce)
        AI by zb
    """
    state_val: Optional[str] = None
    nonce_val: Optional[str] = None
    stack: List[Any] = [obj]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if isinstance(value, (dict, list)):
                    stack.append(value)
                    continue
                if not isinstance(value, str) or not value:
                    continue
                lowered = str(key).lower()
                if state_val is None and lowered in {"state", "oauth_state", "auth_state"}:
                    state_val = value
                elif nonce_val is None and lowered in {"nonce", "oauth_nonce", "auth_nonce"}:
                    nonce_val = value
                if state_val and nonce_val:
                    return state_val, nonce_val
        elif isinstance(current, list):
            stack.extend(current)
    return state_val, nonce_val


def _extract_consent_state_nonce(html: str) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    从 consent 页 HTML 中提取 state / nonce，兼容 Next.js __NEXT_DATA__ 与原始正则。

    参数:
        html: consent 页 HTML 全文
    返回:
        Tuple[Optional[str], Optional[str], List[str]]: (state, nonce, __NEXT_DATA__ 顶层键列表)
        AI by zb
    """
    state_val: Optional[str] = None
    nonce_val: Optional[str] = None
    next_data_keys: List[str] = []

    next_data_match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if next_data_match:
        try:
            payload = json.loads(next_data_match.group(1))
            if isinstance(payload, dict):
                next_data_keys = list(payload.keys())
                state_val, nonce_val = _walk_json_for_state_nonce(payload)
        except Exception:
            pass

    if not state_val:
        legacy_state = re.search(r'["\']state["\']:\s*["\']([^"\' ]+)["\']', html)
        if legacy_state:
            state_val = legacy_state.group(1)
    if not nonce_val:
        legacy_nonce = re.search(r'["\']nonce["\']:\s*["\']([^"\' ]+)["\']', html)
        if legacy_nonce:
            nonce_val = legacy_nonce.group(1)

    return state_val, nonce_val, next_data_keys


def _follow_and_extract_code(
    session: requests.Session,
    url: str,
    oauth_issuer: str,
    max_depth: int = 10,
) -> Optional[str]:
    """
    跟随重定向并提取 OAuth code。

    参数:
        session: HTTP 会话
        url: 初始地址
        oauth_issuer: OAuth 服务根地址
        max_depth: 最大递归深度
    返回:
        Optional[str]: code 参数
        AI by zb
    """
    if max_depth <= 0:
        return None
    if not url:
        return None
    if url.startswith("/"):
        url = f"{oauth_issuer}{url}"
    elif not url.startswith("http"):
        return None
    try:
        response = session.get(
            url,
            headers=NAVIGATE_HEADERS,
            verify=False,
            timeout=15,
            allow_redirects=False,
        )
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            code = _extract_code_from_url(location)
            if code:
                return code
            if not location:
                return None
            if location.startswith("/"):
                location = f"{oauth_issuer}{location}"
            return _follow_and_extract_code(session, location, oauth_issuer, max_depth - 1)
        if response.status_code == 200:
            return _extract_code_from_url(str(response.url))
    except requests.exceptions.ConnectionError as exc:
        match = re.search(r"(https?://localhost[^\s'\"]+)", str(exc))
        if match:
            return _extract_code_from_url(match.group(1))
    except Exception:
        return None
    return None


def _wait_auto_otp(
    email: str,
    mailbox_context: str,
    since_marker: int,
    timeout: int,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    自动轮询邮箱验证码。

    参数:
        email: 邮箱地址
        mailbox_context: 邮箱上下文
        since_marker: 起始时间标记
        timeout: 轮询时长
        logger: 日志器
    返回:
        Optional[str]: OTP 验证码
        AI by zb
    """
    if not mailbox_context:
        return None
    active_logger = logger or get_logger()
    try:
        from app.email_service import wait_for_verification_email_with_marker

        code = wait_for_verification_email_with_marker(
            mailbox_context,
            since_marker=since_marker,
            timeout=timeout,
        )
        if code:
            active_logger.info("[Codex] 自动获取 OTP 成功 | email=%s", email)
            return code
    except Exception as exc:
        active_logger.warning("[Codex] 自动获取 OTP 异常: %s | email=%s", exc, email)
    return None


def _retry_authorize_for_code(
    session: requests.Session,
    authorize_url: str,
    oauth_issuer: str,
    email: str,
    logger: logging.Logger,
    attempts: int = 1,
    retry_delays: Optional[list[int]] = None,
    initial_delay: int = 0,
) -> Optional[str]:
    """
    在已有认证会话稳定后重新触发 OAuth authorize 并提取 code。

    参数:
        session: 当前认证会话
        authorize_url: 原始 authorize URL
        oauth_issuer: OAuth 服务根地址
        email: 登录邮箱
        logger: 日志器
        attempts: 最大尝试次数
        retry_delays: 每次失败后的等待秒数
        initial_delay: 第一次重触发 authorize 前的等待秒数
    返回:
        Optional[str]: OAuth code
        AI by zb
    """
    delays = list(retry_delays) if retry_delays is not None else []
    first_delay = max(int(initial_delay or 0), 0)
    if first_delay > 0:
        logger.info("[Codex] 等待 %d 秒后首次重试获取 auth_code | email=%s", first_delay, email)
        time.sleep(first_delay)
    for attempt in range(1, max(int(attempts or 1), 1) + 1):
        try:
            response = session.get(
                authorize_url,
                headers=NAVIGATE_HEADERS,
                verify=False,
                timeout=30,
                allow_redirects=False,
            )
            location = response.headers.get("Location", "")
            code = _extract_code_from_url(location) or _extract_code_from_url(str(response.url))
            if not code and location:
                next_url = location if location.startswith("http") else f"{oauth_issuer}{location}"
                code = _follow_and_extract_code(session, next_url, oauth_issuer)
            if not code and response.status_code == 200:
                code = _follow_and_extract_code(session, authorize_url, oauth_issuer)
            if code:
                logger.info("[Codex] authorize 重试获取 auth_code 成功 | attempt=%d | email=%s", attempt, email)
                return code
            logger.info(
                "[Codex] authorize 重试未获取 auth_code | HTTP %s | url=%s | location=%s | attempt=%d | email=%s",
                response.status_code,
                str(response.url)[:120],
                str(location)[:200],
                attempt,
                email,
            )
        except requests.exceptions.ConnectionError as exc:
            match = re.search(r"(https?://localhost[^\s'\"]+)", str(exc))
            if match:
                code = _extract_code_from_url(match.group(1))
                if code:
                    logger.info("[Codex] authorize 重试从本地回调异常提取 auth_code | attempt=%d | email=%s", attempt, email)
                    return code
        except Exception as exc:
            logger.warning("[Codex] authorize 重试异常: %s | attempt=%d | email=%s", exc, attempt, email)
        if attempt < attempts:
            delay = int(delays[attempt - 1]) if attempt - 1 < len(delays) else int(delays[-1] if delays else 15)
            if delay > 0:
                logger.info("[Codex] 等待 %d 秒后再次尝试获取 auth_code | next_attempt=%d | email=%s", delay, attempt + 1, email)
                time.sleep(delay)
    return None


def _parse_auth_continue_response(response: requests.Response) -> Tuple[str, str]:
    """
    从认证接口响应中提取下一步地址与页面类型。

    参数:
        response: 认证接口响应
    返回:
        Tuple[str, str]: (continue_url, page_type)
        AI by zb
    """
    continue_url = ""
    page_type = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            continue_url = str(
                data.get("continue_url")
                or data.get("continueUrl")
                or data.get("redirect_to")
                or data.get("redirect_url")
                or ""
            )
            page = data.get("page") if isinstance(data.get("page"), dict) else {}
            page_payload = page.get("payload") if isinstance(page.get("payload"), dict) else {}
            page_type = str(page.get("type") or data.get("page_type") or "")
            verification_mode = str(
                page_payload.get("email_verification_mode")
                or data.get("email_verification_mode")
                or ""
            ).strip().lower()
            if verification_mode in {"passwordless_login", "email_otp", "otp"}:
                page_type = "email_otp_verification"
                continue_url = continue_url or "/email-verification"
    except Exception:
        pass

    response_text = str(getattr(response, "text", "") or "")
    if not continue_url and "email-verification" in response_text:
        continue_url = "/email-verification"
    if not page_type and "email-verification" in continue_url:
        page_type = "email_otp_verification"
    return continue_url, page_type


def _exchange_code_for_token(
    code: str,
    code_verifier: str,
    oauth_issuer: str = OPENAI_AUTH_BASE,
    oauth_client_id: str = OAUTH_CLIENT_ID,
    oauth_redirect_uri: str = OAUTH_REDIRECT_URI,
    proxy: str = "",
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    """
    使用 authorization code 交换 token。

    参数:
        code: OAuth code
        code_verifier: PKCE code_verifier
        oauth_issuer: OAuth 服务根地址
        oauth_client_id: 客户端 ID
        oauth_redirect_uri: 回调地址
        proxy: 代理地址
        logger: 日志器
    返回:
        Optional[Dict[str, Any]]: token 响应
        AI by zb
    """
    active_logger = logger or get_logger()
    session = create_session(proxy=proxy)
    try:
        response = session.post(
            f"{oauth_issuer}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": oauth_redirect_uri,
                "client_id": oauth_client_id,
                "code_verifier": code_verifier,
            },
            verify=False,
            timeout=60,
        )
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, dict) else None
        active_logger.warning("token 交换失败: HTTP %s | %s", response.status_code, response.text[:200])
    except Exception as exc:
        active_logger.warning("token 交换异常: %s", exc)
    return None


def perform_http_oauth_login(
    email: str,
    password: str,
    proxy: str = "",
    otp_mode: str = "auto",
    mailbox_context: str = "",
    otp_provider: Optional[Callable[[str, int, logging.Logger], Optional[str]]] = None,
    otp_wait_timeout: int = 60,
    oauth_issuer: str = OPENAI_AUTH_BASE,
    oauth_client_id: str = OAUTH_CLIENT_ID,
    oauth_redirect_uri: str = OAUTH_REDIRECT_URI,
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    """
    通过纯 HTTP 完成 Codex OAuth 登录。

    参数:
        email: 登录邮箱
        password: 登录密码
        proxy: 代理地址
        otp_mode: OTP 模式，auto 或 manual
        mailbox_context: 邮箱上下文
        otp_provider: 可选手填验证码提供器
        otp_wait_timeout: 自动轮询邮箱验证码的等待时长
        oauth_issuer: OAuth 服务根地址
        oauth_client_id: 客户端 ID
        oauth_redirect_uri: 回调地址
        logger: 日志器
    返回:
        Optional[Dict[str, Any]]: token 响应
        AI by zb
    """
    active_logger = logger or get_logger()
    set_last_login_failure_reason("")
    session = create_session(proxy=proxy)
    device_id = str(uuid.uuid4())
    resolved_mailbox_context = resolve_mailbox_context(email, mailbox_context)
    effective_otp_wait_timeout = resolve_email_wait_timeout({"email": {"wait_timeout": otp_wait_timeout}}, default=60)
    normalized_password = str(password or "").strip()
    passwordless_login = not normalized_password

    session.cookies.set("oai-did", device_id, domain=".auth.openai.com")
    session.cookies.set("oai-did", device_id, domain="auth.openai.com")

    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(32)
    mailbox_marker = create_mailbox_marker_with_skew(30)

    active_logger.info("[Codex] Step A: authorize | email=%s", email)
    authorize_params = {
        "client_id": oauth_client_id,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "codex_cli_simplified_flow": "true",
        "id_token_add_organizations": "true",
        "redirect_uri": oauth_redirect_uri,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "state": state,
    }
    authorize_url = f"{oauth_issuer}/oauth/authorize?{urlencode(authorize_params)}"
    try:
        session.get(
            authorize_url,
            headers=NAVIGATE_HEADERS,
            allow_redirects=True,
            verify=False,
            timeout=30,
        )
    except Exception as exc:
        return fail_oauth_login(f"Step A authorize 失败: {exc}", active_logger, email)

    active_logger.info("[Codex] Step B: 提交邮箱 | email=%s", email)
    headers = dict(COMMON_HEADERS)
    headers["referer"] = f"{oauth_issuer}/log-in"
    if not passwordless_login:
        headers["oai-device-id"] = device_id
        headers.update(generate_datadog_trace())

    sentinel_email = build_sentinel_token(session, device_id, flow="authorize_continue")
    if not sentinel_email:
        return fail_oauth_login("Step B sentinel 生成失败", active_logger, email)
    headers["openai-sentinel-token"] = sentinel_email

    try:
        response = session.post(
            f"{oauth_issuer}/api/accounts/authorize/continue",
            json={"username": {"kind": "email", "value": email}},
            headers=headers,
            verify=False,
            timeout=30,
        )
    except Exception as exc:
        return fail_oauth_login(f"Step B 提交邮箱异常: {exc}", active_logger, email)
    if response.status_code != 200:
        return fail_oauth_login(f"Step B 提交邮箱失败: HTTP {response.status_code} {response.text[:120]}", active_logger, email)
    continue_url, page_type = _parse_auth_continue_response(response)
    if continue_url:
        active_logger.info(
            "[Codex] Step B 结果 | continue_url=%s | page_type=%s | email=%s",
            continue_url[:120],
            page_type,
            email,
        )
    dump_client_auth_session(
        session=session,
        oauth_issuer=oauth_issuer,
        referer=f"{oauth_issuer}/log-in",
        email=email,
        logger=active_logger,
    )

    is_step_b_otp_challenge = page_type == "email_otp_verification" or "email-verification" in continue_url
    if passwordless_login and not is_step_b_otp_challenge:
        continue_url = "/email-verification"
        page_type = "email_otp_verification"
        is_step_b_otp_challenge = True
        active_logger.info("[Codex] 空密码账号使用邮箱验证码登录 | email=%s", email)
    if not is_step_b_otp_challenge:
        active_logger.info("[Codex] Step C: 提交密码 | email=%s", email)
        password_referer = f"{oauth_issuer}/log-in/password"
        if continue_url:
            password_referer = continue_url if continue_url.startswith("http") else f"{oauth_issuer}{continue_url}"
        headers["referer"] = password_referer
        headers.update(generate_datadog_trace())

        sentinel_password = build_sentinel_token(session, device_id, flow="password_verify")
        if not sentinel_password:
            return fail_oauth_login("Step C sentinel 生成失败", active_logger, email)
        headers["openai-sentinel-token"] = sentinel_password

        try:
            response = session.post(
                f"{oauth_issuer}/api/accounts/password/verify",
                json={"password": normalized_password},
                headers=headers,
                verify=False,
                timeout=30,
                allow_redirects=False,
            )
        except Exception as exc:
            return fail_oauth_login(f"Step C 提交密码异常: {exc}", active_logger, email)
        continue_url, page_type = _parse_auth_continue_response(response)
        if response.status_code != 200:
            if response.status_code == 409 and otp_mode == "manual" and not continue_url:
                continue_url = "/email-verification"
                page_type = "email_otp_verification"
            is_otp_challenge = response.status_code == 409 and (
                page_type == "email_otp_verification" or "email-verification" in continue_url
            )
            if not is_otp_challenge:
                return fail_oauth_login(f"Step C 提交密码失败: HTTP {response.status_code} {response.text[:120]}", active_logger, email)
            active_logger.info(
                "[Codex] Step C 返回 OTP 验证挑战: HTTP 409 | continue_url=%s | email=%s",
                continue_url[:120],
                email,
            )

        active_logger.info(
            "[Codex] Step C 结果 | continue_url=%s | page_type=%s | email=%s",
            continue_url[:120],
            page_type,
            email,
        )
    if not continue_url:
        return fail_oauth_login("Step C 未返回 continue_url", active_logger, email)

    if page_type == "email_otp_verification" or "email-verification" in continue_url:
        active_logger.info("[Codex] Step D: 需要 OTP 验证 | email=%s", email)
        verification_url = continue_url if continue_url.startswith("http") else f"{oauth_issuer}{continue_url}"

        try:
            verification_response = session.get(
                verification_url,
                headers=NAVIGATE_HEADERS,
                verify=False,
                timeout=20,
                allow_redirects=True,
            )
            active_logger.info(
                "[Codex] 打开 email-verification 页面: HTTP %s | url=%s | final=%s | email=%s",
                verification_response.status_code,
                verification_url[:80],
                str(verification_response.url)[:120],
                email,
            )
        except Exception as exc:
            active_logger.warning("[Codex] 打开 email-verification 异常: %s | email=%s", exc, email)

        verify_headers = build_auth_json_headers(
            referer=f"{oauth_issuer}/email-verification",
            device_id=device_id,
            include_datadog=not passwordless_login,
            include_device_id=not passwordless_login,
        )

        def send_email_otp(action_label: str) -> Tuple[bool, str]:
            """
            在当前认证会话中请求发送邮箱验证码。

            参数:
                action_label: 日志动作标签
            返回:
                Tuple[bool, str]: 是否成功与提示
                AI by zb
            """
            try:
                send_response = session.get(
                    f"{oauth_issuer}/api/accounts/email-otp/send",
                    headers=verify_headers,
                    verify=False,
                    timeout=30,
                )
                active_logger.info(
                    "[Codex] %s: HTTP %s | email=%s",
                    action_label,
                    send_response.status_code,
                    email,
                )
                if send_response.status_code in {200, 201, 202, 204}:
                    return True, "验证码已发送"
                active_logger.warning(
                    "[Codex] %s 失败详情: HTTP %s | body=%s | email=%s",
                    action_label,
                    send_response.status_code,
                    send_response.text[:200],
                    email,
                )
                return False, f"发送验证码失败: HTTP {send_response.status_code}"
            except Exception as exc:
                active_logger.warning("[Codex] %s 异常: %s | email=%s", action_label, exc, email)
                return False, f"发送验证码异常: {exc}"

        otp_code = None
        if otp_mode == "auto":
            otp_code = _wait_auto_otp(
                email=email,
                mailbox_context=resolved_mailbox_context,
                since_marker=mailbox_marker,
                timeout=effective_otp_wait_timeout,
                logger=active_logger,
            )
            if not otp_code:
                if passwordless_login:
                    active_logger.warning(
                        "[Codex] 未收到初始 passwordless OTP，跳过 email-otp/send fallback 以避免进入 onboarding/add-phone | email=%s",
                        email,
                    )
                else:
                    send_email_otp("OTP fallback send")
                    otp_code = _wait_auto_otp(
                        email=email,
                        mailbox_context=resolved_mailbox_context,
                        since_marker=mailbox_marker,
                        timeout=effective_otp_wait_timeout,
                        logger=active_logger,
                    )

        if not otp_code and otp_mode == "manual":
            def resend_manual_otp() -> Tuple[bool, str]:
                """
                在当前认证会话中重发邮箱验证码。

                返回:
                    Tuple[bool, str]: 是否成功与提示
                    AI by zb
                """
                if passwordless_login:
                    return False, "passwordless Codex 登录不自动重发验证码，避免进入 add-phone/onboarding"
                return send_email_otp("手填 OTP 重发")

            if otp_provider:
                try:
                    otp_code = otp_provider(
                        email,
                        effective_otp_wait_timeout,
                        active_logger,
                        resend_callback=resend_manual_otp,
                    )
                except TypeError:
                    otp_code = otp_provider(email, effective_otp_wait_timeout, active_logger)
            else:
                otp_code = prompt_for_email_otp(email=email, logger=active_logger, timeout=effective_otp_wait_timeout)
        if not otp_code:
            return fail_oauth_login("未获取到邮箱验证码", active_logger, email)

        validate_response = session.post(
            f"{oauth_issuer}/api/accounts/email-otp/validate",
            json={"code": otp_code},
            headers=verify_headers,
            verify=False,
            timeout=30,
        )
        if validate_response.status_code != 200:
            return fail_oauth_login(
                f"OTP 验证失败: HTTP {validate_response.status_code} {validate_response.text[:120]}",
                active_logger,
                email,
            )

        try:
            validate_data = validate_response.json()
            continue_url = str(validate_data.get("continue_url") or continue_url)
            page_type = str(((validate_data.get("page") or {}).get("type")) or "")
        except Exception:
            pass
        active_logger.info(
            "[Codex] OTP 验证成功 | continue_url=%s | page_type=%s | email=%s",
            continue_url[:120],
            page_type,
            email,
        )
        dump_client_auth_session(
            session=session,
            oauth_issuer=oauth_issuer,
            referer=f"{oauth_issuer}/email-verification",
            email=email,
            logger=active_logger,
        )

    auth_session_data = decode_auth_session_cookie(session)
    workspace_id = extract_workspace_id(auth_session_data)
    normalized_page_type = str(page_type or "").strip().lower()
    normalized_continue_url = str(continue_url or "").strip().lower()
    explicit_workspace = normalized_page_type == "workspace" or "/workspace" in normalized_continue_url
    about_you_stage = normalized_page_type in {"about_you", "about-you"} or "/about-you" in normalized_continue_url

    if (explicit_workspace or about_you_stage) and not workspace_id:
        auth_session_data, workspace_id = ensure_workspace_context(
            session=session,
            oauth_issuer=oauth_issuer,
            email=email,
            log_prefix="[Codex]",
            logger=active_logger,
        )

    if explicit_workspace or (workspace_id and about_you_stage):
        continue_url = f"{oauth_issuer}/workspace"
        page_type = "workspace"
        active_logger.info("[Codex] 进入 workspace 阶段 | workspace_id=%s | email=%s", workspace_id or "", email)
        time.sleep(2)
    elif about_you_stage:
        active_logger.info("[Codex] 当前仍处于 about-you/onboarding | email=%s", email)

    if "about-you" in continue_url and not workspace_id:
        about_headers = dict(NAVIGATE_HEADERS)
        about_headers["referer"] = f"{oauth_issuer}/email-verification"
        try:
            response_about = session.get(
                f"{oauth_issuer}/about-you",
                headers=about_headers,
                verify=False,
                timeout=30,
                allow_redirects=True,
            )
            active_logger.info(
                "[Codex] about-you 页面加载: HTTP %s | url=%s | email=%s",
                response_about.status_code,
                str(response_about.url)[:120],
                email,
            )
        except Exception as exc:
            return fail_oauth_login(f"about-you 页面加载异常: {exc}", active_logger, email)

        if "consent" in str(response_about.url) or "organization" in str(response_about.url):
            continue_url = str(response_about.url)
        else:
            first_name, last_name = generate_random_name()
            birthdate = generate_random_birthday()
            create_headers = dict(COMMON_HEADERS)
            create_headers["referer"] = f"{oauth_issuer}/about-you"
            create_headers["oai-device-id"] = device_id
            create_headers.update(generate_datadog_trace())
            response_create = session.post(
                f"{oauth_issuer}/api/accounts/create_account",
                json={"name": f"{first_name} {last_name}", "birthdate": birthdate},
                headers=create_headers,
                verify=False,
                timeout=30,
            )
            active_logger.info(
                "[Codex] about-you create_account: HTTP %s | body=%s | email=%s",
                response_create.status_code,
                response_create.text[:200],
                email,
            )
            if response_create.status_code == 200:
                try:
                    data = response_create.json()
                    continue_url = str(data.get("continue_url") or "")
                except Exception:
                    pass
            elif response_create.status_code == 400 and "already_exists" in response_create.text:
                continue_url = f"{oauth_issuer}/sign-in-with-chatgpt/codex/consent"

            auth_session_data, workspace_id = ensure_workspace_context(
                session=session,
                oauth_issuer=oauth_issuer,
                email=email,
                log_prefix="[Codex]",
                logger=active_logger,
                max_attempts=5,
            )
            if workspace_id:
                continue_url = f"{oauth_issuer}/workspace"
                page_type = "workspace"
                active_logger.info("[Codex] about-you 后补拿到 workspace_id=%s | email=%s", workspace_id, email)

    if "consent" in page_type:
        continue_url = f"{oauth_issuer}/sign-in-with-chatgpt/codex/consent"
    if not continue_url or "email-verification" in continue_url:
        return fail_oauth_login(f"OTP 后仍未进入 Codex 授权页: {continue_url or '无 continue_url'}", active_logger, email)
    if "add-phone" in continue_url.lower():
        return fail_oauth_login(f"OTP 后进入 add-phone，停止当前登录流程: {continue_url}", active_logger, email)

    consent_url = f"{oauth_issuer}{continue_url}" if continue_url.startswith("/") else continue_url
    auth_code = None
    is_consent_url = "consent" in consent_url.lower()

    if not is_consent_url:
        active_logger.info(
            "[Codex] OTP 后进入非 consent 页面，等待会话稳定后重触发 authorize | continue_url=%s | email=%s",
            consent_url[:120],
            email,
        )
        auth_code = _retry_authorize_for_code(
            session=session,
            authorize_url=authorize_url,
            oauth_issuer=oauth_issuer,
            email=email,
            logger=active_logger,
            initial_delay=0,
        )

    if is_consent_url:
        try:
            consent_get_headers = dict(NAVIGATE_HEADERS)
            consent_get_headers["referer"] = f"{oauth_issuer}/email-verification"
            response_consent = session.get(
                consent_url,
                headers=consent_get_headers,
                verify=False,
                timeout=30,
                allow_redirects=False,
            )
            active_logger.info(
                "[Codex] consent GET: HTTP %s | url=%s | location=%s | email=%s",
                response_consent.status_code,
                consent_url[:120],
                str(response_consent.headers.get("Location", ""))[:200],
                email,
            )
            if response_consent.status_code in (301, 302, 303, 307, 308):
                location = response_consent.headers.get("Location", "")
                auth_code = _extract_code_from_url(location)
                if not auth_code:
                    auth_code = _follow_and_extract_code(session, location, oauth_issuer)
                if not auth_code:
                    active_logger.info(
                        "[Codex] consent GET 重定向未带 code 且跟随后仍未提取到 | location=%s | email=%s",
                        str(location)[:200],
                        email,
                    )
            elif response_consent.status_code == 200:
                html = response_consent.text
                state_value, nonce_value, next_data_keys = _extract_consent_state_nonce(html)
                active_logger.info(
                    "[Codex] consent GET 200 | html_len=%d | has_state=%s | has_nonce=%s | next_data_keys=%s | preview=%s | email=%s",
                    len(html),
                    bool(state_value),
                    bool(nonce_value),
                    str(next_data_keys)[:200],
                    html[:200].replace("\n", " ").replace("\r", " "),
                    email,
                )
                if state_value or nonce_value:
                    consent_payload: Dict[str, str] = {"action": "allow"}
                    if state_value:
                        consent_payload["state"] = state_value
                    if nonce_value:
                        consent_payload["nonce"] = nonce_value
                    consent_headers = {
                        "accept": "application/json, text/plain, */*",
                        "content-type": "application/json",
                        "origin": oauth_issuer,
                        "referer": consent_url,
                        "user-agent": USER_AGENT,
                        "oai-device-id": device_id,
                    }
                    post_consent = session.post(
                        consent_url,
                        json=consent_payload,
                        headers=consent_headers,
                        verify=False,
                        timeout=30,
                        allow_redirects=False,
                    )
                    active_logger.info(
                        "[Codex] consent POST: HTTP %s | location=%s | body=%s | email=%s",
                        post_consent.status_code,
                        str(post_consent.headers.get("Location", ""))[:200],
                        str(post_consent.text)[:300].replace("\n", " ").replace("\r", " "),
                        email,
                    )
                    if post_consent.status_code in (301, 302, 303, 307, 308):
                        location = post_consent.headers.get("Location", "")
                        auth_code = _extract_code_from_url(location)
                        if not auth_code:
                            consent_url = location if location.startswith("http") else f"{oauth_issuer}{location}"
                    elif post_consent.status_code == 200:
                        try:
                            consent_data = post_consent.json()
                            redirect_to = str(consent_data.get("redirectTo") or consent_data.get("redirect_url") or "")
                            if redirect_to:
                                auth_code = _extract_code_from_url(redirect_to)
                                if not auth_code:
                                    consent_url = redirect_to
                        except Exception:
                            pass
                else:
                    active_logger.info(
                        "[Codex] consent 页未发现 state/nonce，跳过 page-URL POST 改走 workspace/select fallback | email=%s",
                        email,
                    )
            else:
                auth_code = _extract_code_from_url(str(response_consent.url))
                if not auth_code:
                    auth_code = _follow_and_extract_code(session, str(response_consent.url), oauth_issuer)
        except requests.exceptions.ConnectionError as exc:
            match = re.search(r"(https?://localhost[^\s'\"]+)", str(exc))
            if match:
                auth_code = _extract_code_from_url(match.group(1))
        except Exception as exc:
            active_logger.warning("[Codex] consent 流程异常: %s | email=%s", exc, email)

    if not auth_code:
        session_data = decode_auth_session_cookie(session)
        workspace_id = extract_workspace_id(session_data)
        if not workspace_id:
            dump_data = dump_client_auth_session(
                session=session,
                oauth_issuer=oauth_issuer,
                referer=consent_url,
                email=email,
                logger=active_logger,
            )
            workspace_id = extract_workspace_id(dump_data)
        if session_data:
            active_logger.info(
                "[Codex] auth-session snapshots: %s | email=%s",
                summarize_auth_session_cookies(session),
                email,
            )

        if workspace_id:
            workspace_headers = build_auth_json_headers(referer=consent_url, device_id=device_id)
            try:
                response_workspace = None
                for workspace_attempt in range(1, 2):
                    response_workspace = session.post(
                        f"{oauth_issuer}/api/accounts/workspace/select",
                        json={"workspace_id": workspace_id},
                        headers=workspace_headers,
                        verify=False,
                        timeout=30,
                        allow_redirects=False,
                    )
                    active_logger.info(
                        "[Codex] workspace/select POST: HTTP %s | location=%s | body=%s | attempt=%d | email=%s",
                        response_workspace.status_code,
                        str(response_workspace.headers.get("Location", ""))[:200],
                        str(response_workspace.text)[:300].replace("\n", " ").replace("\r", " "),
                        workspace_attempt,
                        email,
                    )
                    if not (
                        response_workspace.status_code == 400
                        and "no_valid_organizations" in response_workspace.text
                        and workspace_attempt < 1
                    ):
                        break
                    dump_client_auth_session(
                        session=session,
                        oauth_issuer=oauth_issuer,
                        referer=consent_url,
                        email=email,
                        logger=active_logger,
                    )
                    time.sleep(3 * workspace_attempt)
                if response_workspace is None:
                    raise RuntimeError("workspace/select 未返回响应")
                if response_workspace.status_code in (301, 302, 303, 307, 308):
                    location = response_workspace.headers.get("Location", "")
                    auth_code = _extract_code_from_url(location)
                    if not auth_code:
                        auth_code = _follow_and_extract_code(session, location, oauth_issuer)
                elif response_workspace.status_code == 400 and "no_valid_organizations" in response_workspace.text:
                    active_logger.warning(
                        "[Codex] workspace/select 暂无有效组织，继续尝试 authorize/consent fallback | email=%s",
                        email,
                    )
                elif response_workspace.status_code == 200:
                    workspace_data = response_workspace.json()
                    workspace_next = str(workspace_data.get("continue_url") or "")
                    workspace_page = str(((workspace_data.get("page") or {}).get("type")) or "")
                    if workspace_next:
                        full_next = (
                            workspace_next
                            if workspace_next.startswith("http")
                            else f"{oauth_issuer}{workspace_next}"
                        )
                        auth_code = _follow_and_extract_code(session, full_next, oauth_issuer)
                    if not auth_code:
                        auth_code = _follow_and_extract_code(session, authorize_url, oauth_issuer)
                    if not auth_code and ("organization" in workspace_next or "organization" in workspace_page):
                        organization_url = (
                            workspace_next if workspace_next.startswith("http") else f"{oauth_issuer}{workspace_next}"
                        )
                        org_id = None
                        project_id = None
                        workspace_orgs = (
                            (workspace_data.get("data") or {}).get("orgs", [])
                            if isinstance(workspace_data, dict)
                            else []
                        )
                        if workspace_orgs:
                            org_id = (workspace_orgs[0] or {}).get("id")
                            projects = (workspace_orgs[0] or {}).get("projects", [])
                            if projects:
                                project_id = (projects[0] or {}).get("id")

                        if org_id:
                            body: Dict[str, str] = {"org_id": org_id}
                            if project_id:
                                body["project_id"] = project_id
                            organization_headers = build_auth_json_headers(
                                referer=organization_url,
                                device_id=device_id,
                            )
                            response_org = session.post(
                                f"{oauth_issuer}/api/accounts/organization/select",
                                json=body,
                                headers=organization_headers,
                                verify=False,
                                timeout=30,
                                allow_redirects=False,
                            )
                            if response_org.status_code in (301, 302, 303, 307, 308):
                                location = response_org.headers.get("Location", "")
                                auth_code = _extract_code_from_url(location)
                                if not auth_code:
                                    auth_code = _follow_and_extract_code(session, location, oauth_issuer)
                            elif response_org.status_code == 200:
                                organization_data = response_org.json()
                                organization_next = str(organization_data.get("continue_url") or "")
                                if organization_next:
                                    full_next = (
                                        organization_next
                                        if organization_next.startswith("http")
                                        else f"{oauth_issuer}{organization_next}"
                                    )
                                    auth_code = _follow_and_extract_code(session, full_next, oauth_issuer)
                        else:
                            auth_code = _follow_and_extract_code(session, organization_url, oauth_issuer)
            except Exception as exc:
                active_logger.warning("[Codex] workspace/select 流程异常: %s | email=%s", exc, email)

    if not auth_code:
        try:
            response_fallback = session.get(
                consent_url,
                headers=NAVIGATE_HEADERS,
                verify=False,
                timeout=30,
                allow_redirects=True,
            )
            history_chain = " -> ".join(
                f"{h.status_code}:{(h.headers.get('Location') or '')[:80]}"
                for h in (response_fallback.history or [])
            )
            active_logger.info(
                "[Codex] consent 跟随重定向 fallback: HTTP %s | final_url=%s | history=%s | email=%s",
                response_fallback.status_code,
                str(response_fallback.url)[:200],
                history_chain[:300] or "<empty>",
                email,
            )
            auth_code = _extract_code_from_url(str(response_fallback.url))
            if not auth_code and response_fallback.history:
                for history in response_fallback.history:
                    location = history.headers.get("Location", "")
                    auth_code = _extract_code_from_url(location)
                    if auth_code:
                        break
        except requests.exceptions.ConnectionError as exc:
            match = re.search(r"(https?://localhost[^\s'\"]+)", str(exc))
            if match:
                auth_code = _extract_code_from_url(match.group(1))
        except Exception as exc:
            active_logger.warning("[Codex] consent fallback 跟随异常: %s | email=%s", exc, email)

    if not auth_code:
        auth_code = _retry_authorize_for_code(
            session=session,
            authorize_url=authorize_url,
            oauth_issuer=oauth_issuer,
            email=email,
            logger=active_logger,
        )

    if not auth_code:
        return fail_oauth_login("未能获取 auth_code", active_logger, email)

    tokens = _exchange_code_for_token(
        auth_code,
        code_verifier,
        oauth_issuer=oauth_issuer,
        oauth_client_id=oauth_client_id,
        oauth_redirect_uri=oauth_redirect_uri,
        proxy=proxy,
        logger=active_logger,
    )
    if not tokens:
        return fail_oauth_login("token 交换失败", active_logger, email)
    return tokens


def save_token_payload(email: str, token_payload: Dict[str, Any], output_dir: str = "") -> str:
    """
    将 token payload 持久化到本地。

    参数:
        email: 账号邮箱
        token_payload: token 数据
        output_dir: 输出目录
    返回:
        str: 输出文件路径
        AI by zb
    """
    target_dir = Path(output_dir).resolve() if output_dir else DEFAULT_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output_file = target_dir / f"{email}.json"
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(token_payload, file, ensure_ascii=False, indent=2)
    return str(output_file)


def build_sub2api_config(config: Dict[str, Any]) -> Sub2ApiConfig:
    """
    从项目配置构建 Sub2ApiConfig。

    参数:
        config: 项目配置
    返回:
        Sub2ApiConfig: 标准化后的上传配置
        AI by zb
    """
    sub2api_cfg = config.get("sub2api") or {}
    activation_cfg = config.get("activation_api") or {}
    return Sub2ApiConfig(
        base_url=str(sub2api_cfg.get("base_url") or "").strip().rstrip("/"),
        bearer=str(sub2api_cfg.get("bearer") or "").strip(),
        email=str(sub2api_cfg.get("email") or activation_cfg.get("email") or "").strip(),
        password=str(sub2api_cfg.get("password") or activation_cfg.get("password") or "").strip(),
        group_ids=normalize_group_ids(sub2api_cfg.get("group_ids", [2]), default=[2]),
        client_id=OAUTH_CLIENT_ID,
    )


def upload_to_sub2api(
    email: str,
    tokens: Dict[str, Any],
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> bool:
    """
    上传 token 到 Sub2Api。

    参数:
        email: 账号邮箱
        tokens: OAuth tokens
        config: 项目配置
        logger: 日志器
    返回:
        bool: 是否上传成功
        AI by zb
    """
    active_logger = logger or get_logger()
    uploader = Sub2ApiUploader(
        create_session(),
        build_sub2api_config(config),
        active_logger,
    )
    try:
        from app.web_server import get_cached_sub2api_bearer

        uploader.set_bearer_provider(get_cached_sub2api_bearer)
    except Exception:
        pass
    return uploader.push_account(email, tokens)


def run_codex_login(
    email: str,
    password: str,
    config_path: str = "",
    proxy: str = "",
    otp_mode: str = "auto",
    upload: bool = True,
    save_local: bool = True,
    output_dir: str = "",
    logger: Optional[logging.Logger] = None,
) -> CodexRunResult:
    """
    执行 Codex 登录并按需保存、上传。

    参数:
        email: 登录邮箱
        password: 登录密码
        config_path: 配置文件路径
        proxy: 代理地址
        otp_mode: OTP 模式
        upload: 是否上传到 Sub2Api
        save_local: 是否保存本地 token 文件
        output_dir: 输出目录
        logger: 日志器
    返回:
        CodexRunResult: 执行结果
        AI by zb
    """
    active_logger = logger or get_logger()
    config = load_runtime_config(config_path)
    effective_proxy = resolve_proxy(config, proxy)
    otp_wait_timeout = resolve_email_wait_timeout(config, default=60)

    tokens = perform_http_oauth_login(
        email=email,
        password=password,
        proxy=effective_proxy,
        otp_mode=otp_mode,
        otp_wait_timeout=otp_wait_timeout,
        logger=active_logger,
    )
    if not tokens:
        return CodexRunResult(success=False, email=email, error="未获取到 token")

    token_payload = build_token_dict(email, tokens)
    output_file = ""
    if save_local:
        output_file = save_token_payload(email, token_payload, output_dir=output_dir)
        active_logger.info("[Codex] 本地已保存: %s", output_file)

    uploaded = False
    if upload:
        uploaded = upload_to_sub2api(email, tokens, config, logger=active_logger)

    return CodexRunResult(
        success=True,
        email=email,
        uploaded=uploaded,
        output_file=output_file,
        tokens=tokens,
        token_payload=token_payload,
    )


__all__ = [
    "AUTH_JSON_HEADERS",
    "COMMON_HEADERS",
    "CodexRunResult",
    "NAVIGATE_HEADERS",
    "OAUTH_CLIENT_ID",
    "OAUTH_REDIRECT_URI",
    "OPENAI_AUTH_BASE",
    "USER_AGENT",
    "build_auth_json_headers",
    "build_sentinel_token",
    "build_sub2api_config",
    "build_token_dict",
    "create_session",
    "decode_auth_session_cookie",
    "decode_jwt_payload",
    "ensure_workspace_context",
    "extract_workspace_id",
    "generate_datadog_trace",
    "generate_pkce",
    "generate_random_birthday",
    "generate_random_name",
    "get_logger",
    "load_runtime_config",
    "perform_http_oauth_login",
    "prompt_for_email_otp",
    "resolve_proxy",
    "run_codex_login",
    "save_token_payload",
    "summarize_auth_session_cookies",
    "upload_to_sub2api",
]
