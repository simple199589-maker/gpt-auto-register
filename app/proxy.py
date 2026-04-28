# -*- coding: utf-8 -*-
"""
全局代理配置工具。
AI by zb
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _parse_bool(value: Any, default: bool = False) -> bool:
    """
    将代理开关值解析为布尔值。

    参数:
        value: 原始配置值
        default: 默认值
    返回:
        bool: 解析后的布尔值
        AI by zb
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def normalize_proxy_port(value: Any, default: int = 0) -> int:
    """
    将代理端口规范化为 0-65535 范围内的整数。

    参数:
        value: 原始端口值
        default: 默认端口
    返回:
        int: 端口，0 表示未配置
        AI by zb
    """
    try:
        port = int(str(value or "").strip())
    except (TypeError, ValueError):
        return int(default or 0)
    return port if 0 <= port <= 65535 else int(default or 0)


def normalize_proxy_host(value: Any) -> str:
    """
    规范化代理主机，兼容误填的 URL 前缀。

    参数:
        value: 原始主机或代理 URL
    返回:
        str: 主机/IP
        AI by zb
    """
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    for prefix in ("http://", "https://"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    if "/" in text:
        text = text.split("/", 1)[0]
    if ":" in text and text.count(":") == 1:
        host, maybe_port = text.rsplit(":", 1)
        if maybe_port.strip().isdigit():
            return host.strip()
    return text.strip()


def normalize_proxy_url(value: Any) -> str:
    """
    规范化完整代理 URL，缺省协议时补 http://。

    参数:
        value: 原始代理地址
    返回:
        str: requests 可用的代理 URL
        AI by zb
    """
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "socks4://", "socks5://", "socks5h://")):
        return text
    return f"http://{text}"


def build_proxy_url(enabled: bool, host: Any, port: Any) -> str:
    """
    根据开关、主机与端口生成代理 URL。

    参数:
        enabled: 是否启用代理
        host: 代理 IP/主机
        port: 代理端口
    返回:
        str: 代理 URL，未启用或配置不完整时为空
        AI by zb
    """
    if not enabled:
        return ""
    normalized_host = normalize_proxy_host(host)
    normalized_port = normalize_proxy_port(port)
    if not normalized_host or normalized_port <= 0:
        return ""
    return f"http://{normalized_host}:{normalized_port}"


def proxy_config_to_url(proxy_cfg: Any, require_enabled: bool = True) -> str:
    """
    从配置字典解析代理 URL，兼容旧版 proxy.http/proxy.https。

    参数:
        proxy_cfg: proxy 配置段
        require_enabled: 是否要求 enabled=true
    返回:
        str: 代理 URL
        AI by zb
    """
    if not isinstance(proxy_cfg, dict):
        return ""
    legacy_proxy = normalize_proxy_url(proxy_cfg.get("http") or proxy_cfg.get("https") or "")
    has_enabled = "enabled" in proxy_cfg
    enabled = _parse_bool(proxy_cfg.get("enabled"), bool(legacy_proxy) if not has_enabled else False)
    if require_enabled and not enabled:
        return ""
    host = proxy_cfg.get("host") or ""
    port = proxy_cfg.get("port") or 0
    proxy_url = build_proxy_url(True, host, port)
    return proxy_url or legacy_proxy


def current_proxy_url() -> str:
    """
    获取当前全局配置中的代理 URL。

    返回:
        str: 当前代理 URL
        AI by zb
    """
    from app.config import cfg

    return build_proxy_url(
        bool(getattr(cfg.proxy, "enabled", False)),
        getattr(cfg.proxy, "host", ""),
        getattr(cfg.proxy, "port", 0),
    )


def build_requests_proxies(proxy_url: Any = "") -> Dict[str, str]:
    """
    构造 requests proxies 字典。

    参数:
        proxy_url: 代理 URL，空值时读取全局配置
    返回:
        Dict[str, str]: requests 代理配置
        AI by zb
    """
    normalized_url = normalize_proxy_url(proxy_url) if proxy_url else current_proxy_url()
    return {"http": normalized_url, "https": normalized_url} if normalized_url else {}


def current_requests_proxies() -> Optional[Dict[str, str]]:
    """
    获取当前 requests 请求可直接使用的代理参数。

    返回:
        Optional[Dict[str, str]]: 代理字典或 None
        AI by zb
    """
    proxies = build_requests_proxies()
    return proxies or None


def apply_proxy_to_session(session: Any, proxy_url: Any = "") -> Any:
    """
    将代理配置应用到 requests.Session。

    参数:
        session: requests Session
        proxy_url: 指定代理 URL，空值时读取全局配置
    返回:
        Any: 原 Session
        AI by zb
    """
    proxies = build_requests_proxies(proxy_url)
    if proxies:
        session.proxies.update(proxies)
    return session
