"""Fixed service connection for account-scoped commerce reviews; no browser secrets."""
from __future__ import annotations

import hashlib
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, build_opener


class ResearchUnavailable(RuntimeError):
    pass


class ResearchRejected(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def owner_scope(owner: str) -> str:
    return "revenueops:" + hashlib.sha256(owner.encode("utf-8")).hexdigest()


def request_review(method: str, suffix: str, owner: str, payload=None):
    base = os.environ.get("RESEARCH_SERVICE_URL", "").rstrip("/")
    key = os.environ.get("RESEARCH_SERVICE_KEY", "")
    parsed = urlsplit(base)
    if (not owner or len(key) < 32 or not key.isascii() or "\r" in key or "\n" in key
            or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or not (parsed.scheme == "https"
                or (parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port))):
        raise ResearchUnavailable("经营复盘服务尚未配置")
    # Callers construct suffix from fixed paths and parsed UUIDs, never user URLs.
    body = None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    req = Request(base + "/api/internal/research/commerce" + suffix, data=body, method=method,
                  headers={"Authorization": "Bearer " + key, "X-Commerce-Owner": owner_scope(owner),
                           "Content-Type": "application/json", "Accept": "application/json"})
    # Do not forward service credentials through redirects or inherited HTTP proxies.
    from urllib.request import HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=12) as response:
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ResearchUnavailable("复盘响应超过限制")
            return json.loads(data) if data else None
    except HTTPError as exc:
        try:
            if exc.code in (400, 404, 409):
                try:
                    detail = json.loads(exc.read(4096)).get("detail", "请求未完成，请刷新核对")
                    message = detail[:300] if isinstance(detail, str) else "请求未完成，请刷新核对"
                except (ValueError, AttributeError):
                    message = "请求未完成，请刷新核对"
                raise ResearchRejected(exc.code, message) from None
            raise ResearchUnavailable("复盘服务连接未完成，请稍后重试") from None
        finally:
            exc.close()
    except (URLError, TimeoutError, OSError, ValueError):
        raise ResearchUnavailable("复盘服务连接未完成，请稍后重试") from None
