"""监听地址和 CORS 来源。

默认只给本机。远程部署时用环境变量显式打开，不接受 ``*``。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_WILDCARD_HOSTS = {"0.0.0.0", "::", "*"}


class ServerConfigError(ValueError):
    """环境变量里的监听地址或端口无法使用。"""


def resolve_bind(environ: Mapping[str, str] | None = None) -> tuple[str, int]:
    """读取监听地址。``ROCO_HOST`` / ``ROCO_PORT`` 优先于 ``HOST`` / ``PORT``。"""
    env = _env(environ)
    host = _normalize_host(_first(env, ("ROCO_HOST", "HOST"), DEFAULT_HOST))
    if not _valid_host(host):
        raise ServerConfigError(f"监听地址必须是主机名或 IP，当前是 {host!r}")
    port = _parse_port(_first(env, ("ROCO_PORT", "PORT"), str(DEFAULT_PORT)))
    return host, port


def resolve_cors_origins(
    host: str,
    port: int,
    environ: Mapping[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """本机来源始终保留。``ROCO_CORS_ORIGINS`` 追加逗号分隔的公网来源。"""
    origins = list(local_origins(port))
    normalized_host = _normalize_host(host)
    if normalized_host not in _WILDCARD_HOSTS and normalized_host not in _LOOPBACK_HOSTS:
        specific = _origin_for_host(normalized_host, port)
        if specific not in origins:
            origins.append(specific)

    warnings: list[str] = []
    extra = _env(environ).get("ROCO_CORS_ORIGINS", "")
    for raw in str(extra).split(","):
        item = raw.strip()
        if not item:
            continue
        origin = _normalize_origin(item)
        if origin is None:
            warnings.append(
                f"忽略无效的 CORS 来源 {item!r}。"
                "请写完整来源，例如 https://warehouse.example.com，不能使用 *。"
            )
            continue
        if origin not in origins:
            origins.append(origin)
    return origins, warnings


def local_origins(port: int) -> tuple[str, str, str]:
    return (
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    )


def public_bind_warning(host: str) -> str | None:
    """非回环地址能被别的机器访问。令牌接口本身是 GET，挡不住能连上的人。"""
    if _normalize_host(host) in _LOOPBACK_HOSTS:
        return None
    return (
        "警告: 服务监听在非本机地址。"
        "修改接口仍要校验 captures/api.token，"
        "但任何能访问到本服务的人都可以先请求 GET /api/token 拿到令牌。"
        "请用安全组、防火墙或 nginx 限制来源，不要把端口直接暴露到公网。"
        "WinDivert 抓包只在 Windows 上可用。"
    )


def _env(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    if environ is None:
        return os.environ
    return environ


def _first(environ: Mapping[str, str], names: tuple[str, ...], default: str) -> str:
    for name in names:
        value = environ.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _normalize_host(host: str) -> str:
    text = host.strip()
    if len(text) >= 2 and text[0] == "[" and text[-1] == "]":
        return text[1:-1]
    return text


def _valid_host(host: str) -> bool:
    if not host or "://" in host:
        return False
    return not any(char in host for char in "/\\ ?#")


def _parse_port(raw: str) -> int:
    if not raw.isdigit():
        raise ServerConfigError(f"端口必须是 1 到 65535 的整数，当前是 {raw!r}")
    port = int(raw, 10)
    if not 1 <= port <= 65535:
        raise ServerConfigError(f"端口必须是 1 到 65535 的整数，当前是 {raw!r}")
    return port


def _origin_for_host(host: str, port: int) -> str:
    if ":" in host:
        return f"http://[{host}]:{port}"
    return f"http://{host}:{port}"


def _normalize_origin(value: str) -> str | None:
    text = value.strip().rstrip("/")
    if not text or text == "*":
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    if parsed.path not in {"", "/"}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"
