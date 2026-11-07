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
