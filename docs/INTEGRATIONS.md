# OpenCompany integrations

This document describes integration code available in the development branch. It is not evidence that an external account has been connected or tested.

## WooCommerce (first read-only adapter)

The adapter is deliberately limited to the first safe milestone: a business-scoped connection record, an owner-triggered connection test, and bounded reads. It does not create/update products, publish listings, change stock, change order status, send messages, issue refunds, or initiate payments.

### Business isolation

Connections are stored independently under:
- `woocommerce:physical-agency`
- `woocommerce:physical-brand`
- `woocommerce:digital-products`

Never reuse a store's credentials across business units unless the owner has explicitly confirmed that the store belongs to that business. Core is not a commercial store scope.

### Prerequisites

1. A WooCommerce store with the WooCommerce REST API enabled.
2. A dedicated REST API key with **Read** permission only.
3. HTTPS on the public store hostname.
4. A stable `OPENCOMPANY_SECRET_ENCRYPTION_KEY` of at least 32 characters, configured outside the repository and backed up securely. Losing or changing this key makes saved credentials undecryptable.
5. Owner API authentication for every connection or data request.

Do not paste credentials into source code, GitHub issues, comments, chat logs, or screenshots. Credentials are saved only through the authenticated connection endpoint and encrypted in SQLite. The store URL and REST keys are encrypted together. The API never returns their values.

### Owner API

All endpoints require the owner API key using the same authentication convention as the rest of the owner API.

- `PUT /integrations/woocommerce/{business_id}/connection` — validates URL/key shape and encrypts credentials locally. **Does not contact the store.**
- `GET /integrations/woocommerce/{business_id}/status` — reports configuration metadata only.
- `POST /integrations/woocommerce/{business_id}/test` — makes one owner-triggered read-only request for one product to verify access.
- `GET /integrations/woocommerce/{business_id}/products?page=1&per_page=20` — reads up to 50 products per page, pages 1–5.
- `GET /integrations/woocommerce/{business_id}/orders?page=1&per_page=20` — reads up to 50 orders per page, pages 1–5.
- `DELETE /integrations/woocommerce/{business_id}/connection` — removes the saved encrypted credentials.

Supported business IDs: `physical-agency`, `physical-brand`, and `digital-products`.

### Safety properties

- HTTPS only; standard port 443; no URL-embedded credentials, query strings, fragments, or IP-literal hosts.
- DNS results are checked and the TLS connection is pinned to a validated public IP address, preventing a second DNS lookup from redirecting the connection to a private network.
- Redirects are not followed.
- Only fixed WooCommerce REST `GET` product/order paths exist in the adapter.
- Request timeout is 10 seconds; response body is capped at 250 KB; pagination is bounded.
- Product output is minimized to catalogue/stock fields.
- Order output omits billing/shipping names, email, phone, addresses, payment details, notes, and other customer PII.
- Connection changes and read requests are recorded in the tamper-evident audit chain without recording credentials or returned customer data.
- No automatic background polling is enabled. A human owner must initiate each request.
- No provider request occurs when credentials are saved; the separate test/read request is an explicit owner action.

### Current verification status

The adapter, API routes, credential encryption scope, and mocked safety tests are present in the development branch. Tests have **not** been executed because the owner's test/CI pause remains in effect through 2026-12-01. No live WooCommerce store has been connected or contacted. Provider account eligibility, store REST API configuration, revoked-key behavior, real-world response compatibility, and deployment behavior remain unverified.

## Next integration milestones

1. Run the mocked adapter/route suite after the testing pause.
2. Connect one explicitly selected store using a read-only key and owner-triggered test.
3. Verify revoked-key behavior, rate limits, pagination, and audit records.
4. Add import/reconciliation into the matching business's commercial records, with idempotency and no customer PII by default.
5. Only after read-only acceptance, design separate draft-only write workflows with owner approval. Do not add product/order write operations to this adapter.
