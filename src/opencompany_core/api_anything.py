"""Read-only client for the user's private API Anything gateway."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable


class ApiAnythingError(RuntimeError):
    pass


class ApiAnythingClient:
    """Only health, discovery and tier-1 read calls are exposed; no write endpoint exists."""

    def __init__(self, base_url: str, token: str, *, transport: Callable | None = None) -> None:
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            raise ValueError("API Anything base URL must be HTTP(S)")
        if not token or len(token) > 512:
            raise ValueError("API Anything bearer token is required")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._transport = transport or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> "ApiAnythingClient | None":
        base_url = os.environ.get("OPENCOMPANY_API_ANYTHING_BASE_URL")
        token = os.environ.get("OPENCOMPANY_API_ANYTHING_TOKEN")
        if not base_url or not token:
            return None
        return cls(base_url, token)

    def _request(self, method: str, path: str, payload: dict | None = None, *, authenticated: bool = True) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json", "User-Agent": "OpenCompany-ReadOnly-Connector"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._token}"
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method, headers=headers
        )
        try:
            response = self._transport(request, timeout=60)
            raw = response.read(250_000)
            result = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(result, dict):
                raise ApiAnythingError("API Anything returned a non-object response")
            return result
        except urllib.error.HTTPError as exc:
            raise ApiAnythingError(f"API Anything rejected the request (HTTP {exc.code})") from exc
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiAnythingError(f"API Anything request failed safely ({type(exc).__name__})") from exc

    def health(self) -> dict:
        return self._request("GET", "/v1/health", authenticated=False)

    def list_sites(self) -> dict:
        return self._request("GET", "/v1/sites")

    def find_sites(self, query: str) -> dict:
        if not query.strip() or len(query) > 300:
            raise ValueError("search query must contain 1-300 characters")
        return self._request("GET", "/v1/find?q=" + urllib.parse.quote(query, safe=""))

    def list_operations(self, site: str) -> dict:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", site):
            raise ValueError("invalid site identifier")
        return self._request("GET", "/v1/sites/" + urllib.parse.quote(site, safe=""))

    def call_read(self, site: str, operation: str, args: dict, *, max_age_ms: int = 0) -> dict:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", site):
            raise ValueError("invalid site identifier")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", operation):
            raise ValueError("invalid operation identifier")
        if not isinstance(args, dict) or len(json.dumps(args)) > 8000:
            raise ValueError("read operation args must be an object of at most 8000 characters")
        if not 0 <= max_age_ms <= 86_400_000:
            raise ValueError("max_age_ms must be between 0 and one day")
        return self._request(
            "POST",
            f"/v1/call/{urllib.parse.quote(site, safe='')}/{urllib.parse.quote(operation, safe='')}",
            {"args": args, "maxTier": 1, "maxAgeMs": max_age_ms},
        )

    def call_batch(self, calls: list[dict]) -> dict:
        if not 1 <= len(calls) <= 20:
            raise ValueError("batch must contain 1-20 read calls")
        safe_calls = []
        for item in calls:
            if not isinstance(item, dict) or set(item) - {"site", "op", "args", "id"}:
                raise ValueError("invalid batch call shape")
            site, operation, args = item.get("site"), item.get("op"), item.get("args", {})
            if not isinstance(site, str) or not isinstance(operation, str) or not isinstance(args, dict):
                raise ValueError("batch calls require site, op and object args")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", site):
                raise ValueError("invalid site identifier")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", operation):
                raise ValueError("invalid operation identifier")
            safe_calls.append({"site": site, "op": operation, "args": args, "id": item.get("id")})
        return self._request(
            "POST", "/v1/batch", {"calls": safe_calls, "concurrency": min(4, len(safe_calls)), "maxTier": 1}
        )
