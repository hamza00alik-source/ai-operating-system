"""Strictly read-only WooCommerce REST adapter.

The adapter exposes only product/order GET operations, rejects non-HTTPS and
non-public host forms, does not follow redirects, bounds response size and
pagination, and returns minimized records without customer PII.
"""
from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable


class WooCommerceReadError(RuntimeError):
    pass


class _PinnedPublicHTTPSConnection(http.client.HTTPSConnection):
    """Resolve once, reject non-public addresses, and pin the TLS socket to that IP."""

    def connect(self) -> None:
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        candidates = []
        for item in addresses:
            address = item[4][0]
            parsed = ipaddress.ip_address(address)
            if not parsed.is_global:
                raise WooCommerceReadError("WooCommerce hostname resolved to a non-public network address.")
            candidates.append((item[0], item[4]))
        if not candidates:
            raise WooCommerceReadError("WooCommerce hostname did not resolve to a public address.")
        last_error = None
        for family, sockaddr in candidates:
            try:
                raw = socket.create_connection(sockaddr, self.timeout, self.source_address)
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
            except OSError as exc:
                last_error = exc
        if last_error:
            raise last_error


class WooCommerceReadOnlyClient:
    MAX_RESPONSE_BYTES = 250_000

    def __init__(
        self, store_url: str, consumer_key: str, consumer_secret: str,
        *, transport: Callable | None = None,
    ) -> None:
        parsed = urllib.parse.urlsplit(store_url.strip())
        host = (parsed.hostname or "").casefold().rstrip(".")
        if (
            parsed.scheme != "https" or not host or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)
            or host in {"localhost"} or host.endswith((".localhost", ".local", ".internal"))
        ):
            raise ValueError("WooCommerce store URL must be a public HTTPS origin/path on port 443 without credentials, query or fragment.")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("WooCommerce store URL must use a DNS hostname, not an IP address.")
        if not consumer_key.startswith("ck_") or not consumer_secret.startswith("cs_"):
            raise ValueError("WooCommerce REST credentials must use the expected consumer-key format.")
        if len(consumer_key) > 256 or len(consumer_secret) > 256:
            raise ValueError("WooCommerce credentials exceed the supported length.")
        self.base_url = store_url.strip().rstrip("/")
        self._authorization = "Basic " + base64.b64encode(
            f"{consumer_key}:{consumer_secret}".encode()
        ).decode("ascii")
        self._transport = transport

    def _get(self, resource: str, *, page: int, per_page: int) -> list[dict]:
        if resource not in {"products", "orders"}:
            raise ValueError("Unsupported WooCommerce read resource.")
        if not 1 <= page <= 5 or not 1 <= per_page <= 50:
            raise ValueError("Read pagination is limited to pages 1-5 and 1-50 records.")
        query = urllib.parse.urlencode({"page": page, "per_page": per_page})
        url = self.base_url + "/wp-json/wc/v3/" + resource + "?" + query
        request = urllib.request.Request(url, method="GET", headers={
            "Accept": "application/json",
            "Authorization": self._authorization,
            "User-Agent": "OpenCompany-WooCommerce-ReadOnly/1.0",
        })
        connection = None
        try:
            if self._transport is not None:
                response = self._transport(request, timeout=10)
            else:
                parsed = urllib.parse.urlsplit(url)
                connection = _PinnedPublicHTTPSConnection(parsed.hostname, timeout=10, context=ssl.create_default_context())
                connection.request("GET", parsed.path + "?" + parsed.query, headers=dict(request.header_items()))
                response = connection.getresponse()
                if response.status < 200 or response.status >= 300:
                    raise WooCommerceReadError(f"WooCommerce rejected the read request (HTTP {response.status}).")
            raw = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(raw) > self.MAX_RESPONSE_BYTES:
                raise WooCommerceReadError("WooCommerce response exceeded the safe size limit.")
            value = json.loads(raw.decode("utf-8")) if raw else []
            if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                raise WooCommerceReadError("WooCommerce returned an unexpected response shape.")
            return value
        except WooCommerceReadError:
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, http.client.HTTPException,
                ssl.SSLError, socket.gaierror, TimeoutError, OSError,
                UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WooCommerceReadError(f"WooCommerce read request failed safely ({type(exc).__name__}).") from exc
        finally:
            if connection is not None:
                connection.close()

    def products(self, *, page: int = 1, per_page: int = 20) -> dict:
        rows = self._get("products", page=page, per_page=per_page)
        return {"page": page, "per_page": per_page, "count": len(rows), "products": [
            {key: row.get(key) for key in (
                "id", "name", "type", "status", "sku", "price",
                "stock_status", "manage_stock", "stock_quantity", "date_modified",
            )} for row in rows
        ]}

    def orders(self, *, page: int = 1, per_page: int = 20) -> dict:
        rows = self._get("orders", page=page, per_page=per_page)
        return {"page": page, "per_page": per_page, "count": len(rows), "orders": [
            {
                "id": row.get("id"), "status": row.get("status"),
                "currency": row.get("currency"), "total": row.get("total"),
                "date_created": row.get("date_created"),
                "line_items": [
                    {"name": item.get("name"), "quantity": item.get("quantity")}
                    for item in (row.get("line_items") or [])[:30]
                    if isinstance(item, dict)
                ],
            } for row in rows
        ]}
