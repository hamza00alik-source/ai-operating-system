"""Owner-triggered, read-only connection checks for WordPress and WooCommerce.

Credentials are supplied by the owner from the control dashboard, tested with a
GET request, then stored in the encrypted credential vault. No writes occur.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit


class IntegrationCheckError(RuntimeError):
    pass


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            raise IntegrationCheckError("Cross-origin redirect blocked.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _site_origin(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Store URL must be a public HTTPS URL without embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("Store URL must not contain a query string or fragment.")
    if parsed.path not in {"", "/"}:
        raise ValueError("Enter the site origin only, for example https://example.com.")
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local and private network hosts are not allowed.")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("Private and non-public IP addresses are not allowed.")
    except ValueError as exc:
        if "not allowed" in str(exc):
            raise
    try:
        for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM):
            address = ipaddress.ip_address(item[4][0])
            if not address.is_global:
                raise ValueError("Store hostname resolves to a non-public address.")
    except socket.gaierror as exc:
        raise ValueError("Store hostname could not be resolved.") from exc
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def _get_json(url: str, username: str, password: str) -> dict | list:
    token = base64.b64encode((username + ":" + password).encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, headers={
        "Authorization": "Basic " + token,
        "Accept": "application/json",
        "User-Agent": "AIOS-owner-connection-check/1.0",
    }, method="GET")
    try:
        with urllib.request.build_opener(_SameOriginRedirect()).open(req, timeout=20) as response:
            raw = response.read(512_001)
            if len(raw) > 512_000:
                raise IntegrationCheckError("Platform response exceeded 512 KB.")
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, (dict, list)):
                raise IntegrationCheckError("Platform returned an unexpected response.")
            return data
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise IntegrationCheckError("The platform rejected the credentials or the account lacks the required read permission.") from exc
        if exc.code == 404:
            raise IntegrationCheckError("The expected REST API endpoint was not found. Check the site URL and REST API availability.") from exc
        raise IntegrationCheckError(f"Platform returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrationCheckError(f"Could not verify the platform connection ({type(exc).__name__}).") from exc


def verify_connection(provider: str, secret: str, config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("Connection configuration must be an object.")
    origin = _site_origin(config.get("site_url", ""))
    if not isinstance(secret, str) or len(secret) < 8 or len(secret) > 4096:
        raise ValueError("Credential must contain between 8 and 4096 characters.")
    if provider == "wordpress":
        username = str(config.get("username", "")).strip()
        if not username or len(username) > 200:
            raise ValueError("WordPress username is required.")
        data = _get_json(origin + "/wp-json/wp/v2/users/me?context=edit", username, secret)
        if not isinstance(data, dict) or not data.get("id"):
            raise IntegrationCheckError("WordPress did not return an authenticated user profile.")
        return {"provider": provider, "connected": True, "site_url": origin,
                "account": data.get("name") or username, "capability": "authenticated WordPress REST read access"}
    if provider == "woocommerce":
        consumer_key = str(config.get("consumer_key", "")).strip()
        if not consumer_key or len(consumer_key) > 256:
            raise ValueError("WooCommerce consumer key is required.")
        data = _get_json(origin + "/wp-json/wc/v3/products?per_page=1", consumer_key, secret)
        if not isinstance(data, list):
            raise IntegrationCheckError("WooCommerce did not return a products list.")
        return {"provider": provider, "connected": True, "site_url": origin,
                "capability": "WooCommerce REST read access", "sampled_products": len(data)}
    raise ValueError("Direct connection checks currently support WordPress and WooCommerce. Other providers need their own OAuth/API adapter.")
