"""Read-only WooCommerce REST client.

Only catalog metadata and coarse order/payment status are exposed. No create,
update, delete, refund, payment, customer, or publishing methods exist here.
"""
import base64
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request


class WooCommerceNotConfigured(RuntimeError):
    pass


class WooCommerceReadError(RuntimeError):
    pass


class WooCommerceWriteDisabled(RuntimeError):
    pass


class WooCommerceWriteError(RuntimeError):
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
        if base_url and key and secret:
            return cls(base_url, key, secret)
        try:
            from ai_os.credential_vault import (
                CredentialVaultError, resolve_unique_provider_credential,
            )
            stored = resolve_unique_provider_credential("woocommerce")
        except (CredentialVaultError, ValueError, sqlite3.OperationalError):
            raise WooCommerceNotConfigured(
                "WooCommerce credentials are not configured in the environment or as one unambiguous vault entry; no request was made."
            )
        base_url = str(stored.get("url") or stored.get("store_url") or "").strip()
        key = str(stored.get("consumer_key") or "").strip()
        secret = str(stored.get("consumer_secret") or "").strip()
        if not (base_url and key and secret):
            raise WooCommerceNotConfigured(
                "Stored WooCommerce credential must contain url, consumer_key, and consumer_secret; no request was made."
            )
        return cls(base_url, key, secret)

    @staticmethod
    def status() -> dict:
        environment_configured = all(os.getenv(name, "").strip() for name in (
            "AI_OS_WOOCOMMERCE_URL",
            "AI_OS_WOOCOMMERCE_CONSUMER_KEY",
            "AI_OS_WOOCOMMERCE_CONSUMER_SECRET",
        ))
        try:
            from ai_os.credential_vault import list_credentials
            active_vault_credentials = [
                item for item in list_credentials(provider_id="woocommerce")
                if item["status"] != "revoked"
            ]
        except Exception:
            active_vault_credentials = []
        vault_configured = len(active_vault_credentials) == 1
        configured = environment_configured or vault_configured
        credential_source = (
            "environment" if environment_configured else
            "vault" if vault_configured else
            "ambiguous_vault_entries" if len(active_vault_credentials) > 1 else
            "none"
        )
        draft_writes = (
            configured
            and os.getenv("AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED", "false").strip().lower() == "true"
            and os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() == "true"
        )
        return {
            "configured": configured,
            "credential_source": credential_source,
            "credential_verified": False,
            "mode": "read_only_with_optional_approved_drafts",
            "capabilities": ["product_catalog_read", "order_status_read"] + (
                ["create_unpublished_product_draft"] if draft_writes else []
            ),
            "writes_enabled": draft_writes,
            "published_writes_enabled": False,
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
        allowed = ("id", "status", "date_created", "date_paid", "currency", "total")
        result = []
        for row in rows:
            item = {key: row.get(key) for key in allowed}
            item["payment_status"] = "paid" if row.get("date_paid") else "not_confirmed"
            result.append(item)
        return result

    def create_product_draft(self, *, name: str, description: str, regular_price: str) -> dict:
        """Create a WooCommerce product draft only; publishing is never allowed."""
        if (
            os.getenv("AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED", "false").strip().lower() != "true"
            or os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() != "true"
        ):
            raise WooCommerceWriteDisabled("WooCommerce draft writes require both explicit feature flags.")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Product name must contain 1 to 200 characters.")
        if not isinstance(description, str) or len(description.encode("utf-8")) > 12000:
            raise ValueError("Product description must not exceed 12,000 UTF-8 bytes.")
        if not isinstance(regular_price, str) or len(regular_price) > 16:
            raise ValueError("Product price must be a short decimal string.")
        from decimal import Decimal, InvalidOperation
        try:
            price = Decimal(regular_price)
        except InvalidOperation as exc:
            raise ValueError("Product price must be a valid non-negative decimal.") from exc
        if not price.is_finite() or price < 0:
            raise ValueError("Product price must be a valid non-negative decimal.")
        normalized_price = format(price, "f")
        if len(normalized_price) > 12:
            raise ValueError("Product price exceeds the supported 12-character amount limit.")
        payload = json.dumps({
            "name": name.strip(),
            "description": description,
            "regular_price": normalized_price,
            "status": "draft",
        }, ensure_ascii=False, allow_nan=False).encode("utf-8")
        url = urllib.parse.urljoin(self.base_url, "products")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": self.authorization,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ai-operating-system-approved-product-draft/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2000001)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WooCommerceWriteError(
                "WooCommerce product draft creation failed; inspect the store and audit trail before retrying."
            ) from exc
        if len(raw) > 2000000:
            raise WooCommerceWriteError("WooCommerce draft response exceeded the 2 MB safety limit.")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WooCommerceWriteError("WooCommerce returned invalid JSON after draft creation.") from exc
        if not isinstance(result, dict) or result.get("status") != "draft":
            raise WooCommerceWriteError("WooCommerce did not confirm an unpublished product draft; inspect the store before retrying.")
        return {
            "id": result.get("id"),
            "status": result.get("status"),
            "name": result.get("name"),
            "permalink": result.get("permalink"),
        }
