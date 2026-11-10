"""Owner-supervised, read-only bridge to an API Anything HTTP server.

The API Anything token is read only from the Railway environment and is never
returned by this module. All website calls use /v1/call (never /v1/write)
and are forced to maxTier=1 to avoid browser fallbacks.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit

_MAX_RESPONSE_BYTES = 1_000_000
_TIMEOUT_SECONDS = 25
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$", re.IGNORECASE)


class WebsiteApiUnavailable(RuntimeError):
    pass


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlsplit(req.full_url)
        new = urlsplit(newurl)
        if (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            raise WebsiteApiUnavailable("API Anything attempted a cross-origin redirect; request blocked.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _configuration() -> tuple[str, str]:
    base = os.getenv("AI_OS_API_ANYTHING_URL", "").strip().rstrip("/")
    token = os.getenv("AI_OS_API_ANYTHING_TOKEN", "").strip()
    if not base or not token:
        raise WebsiteApiUnavailable("API Anything is not configured. Set its private URL and bearer token in Railway Variables.")
    parsed = urlsplit(base)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise WebsiteApiUnavailable("API Anything URL must be an HTTP(S) origin without embedded credentials.")
    if parsed.query or parsed.fragment:
        raise WebsiteApiUnavailable("API Anything URL must not contain a query string or fragment.")
    if parsed.path not in {"", "/"}:
        raise WebsiteApiUnavailable("API Anything URL must be the service origin, without a path.")
    return base, token


def _request(method: str, path: str, body: dict | None = None, *, authenticated: bool = True):
    base, token = _configuration()
    headers = {"Accept": "application/json"}
    if authenticated:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_SameOriginRedirect())
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise WebsiteApiUnavailable("API Anything response exceeded the 1 MB safety limit.")
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", "replace")
        if exc.code == 401:
            raise WebsiteApiUnavailable("API Anything rejected its bearer token. Check Railway Variables.") from exc
        raise WebsiteApiUnavailable(f"API Anything returned HTTP {exc.code}: {detail[:500]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WebsiteApiUnavailable(f"Could not reach API Anything: {type(exc).__name__}.") from exc


def status() -> dict:
    try:
        health = _request("GET", "/v1/health", authenticated=False)
        return {
            "configured": True,
            "connected": bool(health.get("ok")),
            "version": health.get("version"),
            "service": "API Anything",
            "execution_policy": "read-only HTTP calls; maxTier=1; writes disabled",
        }
    except WebsiteApiUnavailable as exc:
        return {
            "configured": bool(os.getenv("AI_OS_API_ANYTHING_URL") and os.getenv("AI_OS_API_ANYTHING_TOKEN")),
            "connected": False,
            "error": str(exc),
            "service": "API Anything",
            "execution_policy": "read-only HTTP calls; maxTier=1; writes disabled",
        }


def list_sites() -> dict:
    return _request("GET", "/v1/sites")


def find_sites(query: str) -> dict:
    query = query.strip()
    if not query or len(query) > 300:
        raise ValueError("Search query must contain 1–300 characters.")
    return _request("GET", "/v1/find?" + urllib.parse.urlencode({"q": query}))


def call_read(site: str, operation: str, args: dict, fields: list[str] | None = None) -> dict:
    if not _NAME_RE.fullmatch(site) or not _NAME_RE.fullmatch(operation):
        raise ValueError("Site and operation names may contain only letters, numbers, dot, underscore and hyphen.")
    if not isinstance(args, dict) or len(json.dumps(args, ensure_ascii=False)) > 20_000:
        raise ValueError("Operation arguments must be a JSON object no larger than 20 KB.")
    body = {"args": args, "maxTier": 1}
    if fields is not None:
        if not isinstance(fields, list) or len(fields) > 40 or any(not isinstance(x, str) or len(x) > 100 for x in fields):
            raise ValueError("Requested fields must be a list of at most 40 short strings.")
        body["view"] = {"fields": fields}
    # Deliberately call only the read endpoint. Never expose /v1/write or allowTier 2/3.
    return _request("POST", f"/v1/call/{urllib.parse.quote(site, safe='')}/{urllib.parse.quote(operation, safe='')}", body)


def list_operations(site: str) -> dict:
    if not _NAME_RE.fullmatch(site):
        raise ValueError("Site name may contain only letters, numbers, dot, underscore and hyphen.")
    return _request("GET", f"/v1/sites/{urllib.parse.quote(site, safe='')}")
