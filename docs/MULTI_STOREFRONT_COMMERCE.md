# Multi-storefront commerce foundation

## Current scope

The commerce layer provides an owner-authenticated storefront status inventory and a validated, local-only listing-packet generator. It does not contact marketplace APIs, upload files, publish listings, change prices, process orders, message customers, or move money.

Registered channels are WooCommerce, Gumroad, itch.io, CGTrader, Fab, and Etsy. WooCommerce reuses the existing read-only catalog/order-status connector and its separately gated unpublished-product draft action. Other channels remain manual or partially manual until API, country eligibility, payout/KYC, fee, and permission requirements are verified.

## API

- GET /commerce/storefronts returns channel capability/status metadata. A credentials_present_unverified state means only that expected environment variables are non-empty; it is not a successful login or live API check.
- POST /commerce/listing-packets validates product metadata and returns a draft packet for a selected channel. It performs no upload or publication.

The routes inherit the application's owner authentication and request audit middleware.

## Channel limitations

- Gumroad: its help center currently states that creating products or uploading content through the API is not available. Use the listing packet for manual setup until that changes.
- itch.io: the server-side API supports account/game queries. Uploading builds is done with butler tooling; the server API is not treated as a product-create endpoint here. An owner-operated upload flow remains separate.
- CGTrader / Fab: no automated write connector is enabled. Confirm seller onboarding, country-specific payouts, permissions, and current API terms before implementation.
- Etsy: deferred until upfront listing/transaction costs and payment onboarding have been reviewed and explicitly approved.
- WooCommerce: existing integration remains read-only for inventory/orders with a separate exact-owner-approved product-draft action. No publication or fulfillment is enabled.

## Security and release rules

- Never commit access tokens or API credentials.
- Credential presence is not verified connectivity.
- No secrets are returned by the status API.
- No channel has automated publishing in this release.
- Every external upload or publication requires a future channel-specific adapter, idempotency/reconciliation tests, exact-scope CEO request, owner approval, and explicit execution.
- Unsupported APIs must continue to produce exportable manual listing packets rather than simulated automation.


## Implemented local commerce operations

The current branch also adds a SQLite-backed canonical product catalog, per-channel listing-packet records, an idempotent normalized order ledger, and a fulfillment review queue.

- POST /commerce/catalog/products creates a local product in draft status.
- GET /commerce/catalog/products lists the canonical catalogue.
- POST /commerce/catalog/products/{product_id}/listing-packets?channel=... creates a local channel-specific packet.
- POST /commerce/listings/{listing_id}/approve-manual-upload requires the configured owner identity and marks the packet approved for manual upload only. It does not upload or publish.
- GET /commerce/listings lists stored packets and status.
- POST /commerce/webhooks/woocommerce accepts an HMAC-SHA256 signed WooCommerce webhook using AI_OS_WOOCOMMERCE_WEBHOOK_SECRET and X-WC-Webhook-Signature.
- GET /commerce/orders lists minimized normalized orders. Customer billing and shipping PII are not stored.
- GET /commerce/fulfillment lists fulfillment review items. No delivery is performed.
- GET /commerce/overview feeds the owner dashboard.

Order events are idempotent on (channel, external_order_id). A WooCommerce order is considered paid only when date_paid is present in the webhook payload; processing/completed status alone is not sufficient. Even a paid order moves only to ready_after_payment_check, never to auto-fulfilled.

## Required deployment configuration

- Set AI_OS_WOOCOMMERCE_WEBHOOK_SECRET to the exact secret configured in the WooCommerce webhook.
- Configure a WooCommerce webhook for the order event and point it to /commerce/webhooks/woocommerce on the deployed HTTPS service.
- The endpoint verifies the signature before parsing and storing the payload. It is exempt from owner bearer-token middleware only because it performs its own HMAC signature check.
- Configure owner API token and database persistence separately. Do not commit secrets.
- Test with a non-production webhook or sample signed request before enabling the production webhook.

## Not yet implemented

- Marketplace account OAuth/token verification and country-specific payout onboarding.
- Gumroad/itch.io/CGTrader/Fab/Etsy live order connectors.
- Automated digital file hosting, expiring download links, license issuance, email delivery, and retries.
- Automated payout statement imports, per-sale fee allocation, refund/dispute reconciliation, tax reporting, and bank/Payoneer settlement verification. A manual owner-entered payout record exists, but it is not an automated reconciliation.
- Automated product sync or publication. The owner dashboard reports status but does not publish.


## Entitlement mapping and payout records

- POST /commerce/listings/{listing_id}/map-external-id is owner-only. After a listing packet is approved and manually published, the owner records the marketplace's product ID. This is a local mapping; it does not contact the marketplace.
- For an order whose payment timestamp is confirmed, matching line-item IDs create idempotent internal entitlement records in awaiting_manual_delivery state.
- GET /commerce/entitlements lists internal entitlements. No download URL, license key, email, or customer delivery is generated.
- POST /commerce/payouts/records records a payout statement row entered by the owner. Gross minus fees must equal net; duplicate provider payout IDs are rejected.
- A new payout record starts as recorded_unverified. POST /commerce/payouts/{payout_id}/confirm-received requires owner authentication and records the owner's confirmation that funds arrived. It does not access a bank, Payoneer, or marketplace payout account.
- GET /commerce/payouts lists statement records. This is a manual reconciliation ledger, not automated statement ingestion or proof of settlement.
