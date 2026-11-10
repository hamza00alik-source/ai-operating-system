"""Read-only seller-account verification for supported marketplaces."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class MarketplaceCheckError(RuntimeError):
    pass


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            raise MarketplaceCheckError("Cross-origin marketplace redirect blocked.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_playerauctions(api_secret: str, config: dict) -> dict:
    """Authenticate using the documented HMAC-SHA256 signature and read one offer."""
    api_key = str((config or {}).get("api_key", "")).strip()
    if not api_key or len(api_key) > 512:
        raise ValueError("PlayerAuctions API key is required.")
    if not isinstance(api_secret, str) or len(api_secret) < 8 or len(api_secret) > 1024:
        raise ValueError("PlayerAuctions API secret must contain between 8 and 1024 characters.")
    timestamp = str(int(time.time()))
    body = ""
    canonical = api_key + timestamp + body
    signature = hmac.new(api_secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    query = urllib.parse.urlencode({"pageIndex": 1, "pageSize": 1})
    url = "https://seller-api.playerauctions.com/api/v1/offers?" + query
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "AIOS-owner-marketplace-check/1.0",
        "X-PA-API-KEY": api_key,
        "X-PA-TIMESTAMP": timestamp,
        "X-PA-SIGN": signature,
    }, method="GET")
    try:
        with urllib.request.build_opener(_SameOriginRedirect()).open(request, timeout=20) as response:
            raw = response.read(256001)
            if len(raw) > 256000:
                raise MarketplaceCheckError("PlayerAuctions response exceeded 256 KB.")
            data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise MarketplaceCheckError("PlayerAuctions rejected the API key/signature or account permissions.") from exc
        raise MarketplaceCheckError("PlayerAuctions returned HTTP " + str(exc.code) + ".") from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MarketplaceCheckError("Could not verify PlayerAuctions connection (" + type(exc).__name__ + ").") from exc
    if not isinstance(data, dict) or data.get("code") != 10000:
        message = data.get("message", "Unexpected API response.") if isinstance(data, dict) else "Unexpected API response."
        raise MarketplaceCheckError("PlayerAuctions API check failed: " + str(message)[:300])
    result = data.get("data") or {}
    return {"provider": "playerauctions", "connected": True,
            "account": "PlayerAuctions seller account",
            "capability": "read-only seller offer access",
            "sampled_offers": len(result.get("items") or []),
            "external_actions": "GET only; no offers, pricing, inventory or orders changed"}
