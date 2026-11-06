"""Read-only WooCommerce REST client.

Only catalog metadata and coarse order/payment status are exposed. No create,
update, delete, refund, payment, customer, or publishing methods exist here.
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class WooCommerceNotConfigured(RuntimeError):
    pass


class WooCommerceReadError(RuntimeError):
    pass


class WooCommerceReadOnlyClient:
    def __init__(self, base_url: str, consumer_key: str, consumer_secret: str,
                 *, timeout: int = 15):
        parsed = urllib.parse.urlparse(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("WooCommerce base URL must be HTTPS without embedded credentials, query, or fragment.")
        self.base_url = base_url.rstrip("/") + "/"
        credentials = (consumer_key + ":" + consumer_secret).encode("utf-8")
        self.authorization = "Basic " + base64.b64encode(credentials).decode("ascii")
        self.timeout = max(3, min(int(timeout), 30))

    @classmethod
    def from_environment(cls):
        base_url = os.getenv("AI_OS_WOOCOMMERCE_URL", "").strip()
        key = os.getenv("AI_OS_WOOCOMMERCE_CONSUMER_KEY", "").strip()
        secret = os.getenv("AI_OS_WOOCOMMERCE_CONSUMER_SECRET", "").strip()
        if not (base_url and key and secret):
            raise WooCommerceNotConfigured(
                "WooCommerce read-only credentials are not configured; no request was made."
            )
        return cls(base_url, key, secret)

    @staticmethod
    def status() -> dict:
        configured = all(os.getenv(name, "").strip() for name in (
            "AI_OS_WOOCOMMERCE_URL",
            "AI_OS_WOOCOMMERCE_CONSUMER_KEY",
            "AI_OS_WOOCOMMERCE_CONSUMER_SECRET",
        ))
        return {
            "configured": configured,
            "mode": "read_only",
            "capabilities": ["product_catalog_read", "order_status_read"],
            "writes_enabled": False,
            "customer_data_exposed": False,
        }

    def _get(self, resource: str, params: dict) -> list[dict]:
        query = urllib.parse.urlencode(params)
        url = urllib.parse.urljoin(self.base_url, resource) + "?" + query
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": self.authorization,
                "Accept": "application/json",
                "User-Agent": "ai-operating-system-readonly/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WooCommerceReadError(
                "WooCommerce read request failed; credentials and response were not logged."
            ) from exc
        if len(raw) > 2_000_000:
            raise WooCommerceReadError("WooCommerce response exceeded the 2 MB safety limit.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WooCommerceReadError("WooCommerce returned invalid JSON.") from exc
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise WooCommerceReadError("WooCommerce returned an unexpected response shape.")
        return payload

    def list_products(self, *, page: int = 1, per_page: int = 20) -> list[dict]:
        page = max(1, min(int(page), 1000))
        per_page = max(1, min(int(per_page), 50))
        rows = self._get("products", {"page": page, "per_page": per_page})
        allowed = ("id", "name", "sku", "status", "price", "permalink", "stock_status")
        return [{key: row.get(key) for key in allowed} for row in rows]

    def list_order_statuses(self, *, page: int = 1, per_page: int = 20,
                            status: str | None = None) -> list[dict]:
        page = max(1, min(int(page), 1000))
        per_page = max(1, min(int(per_page), 50))
        params = {"page": page, "per_page": per_page}
        if status:
            if status not in {"pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"}:
                raise ValueError("Unsupported WooCommerce order status filter.")
            params["status"] = status
        rows = self._get("orders", params)
        allowed = ("id", "status", "date_created", "currency", "total")
        return [{key: row.get(key) for key in allowed} for row in rows]
