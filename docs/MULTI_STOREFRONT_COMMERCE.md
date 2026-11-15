# Multi-storefront commerce foundation

## Purpose

OpenCompany keeps one canonical product and order record inside its own business-scoped system. Storefronts are external sales channels, not separate sources of truth.

The first implementation increment adds:
- A provider-neutral channel registry.
- Explicit business-unit applicability for each channel.
- A capability matrix whose external values remain unverified until supported by official documentation and an owner-authorized account check.
- An internal listing-draft contract.
- Owner-authenticated read-only channel endpoints.

## Initial channel plan

| Channel | Intended role | Current state |
|---|---|---|
| WooCommerce | Primary owned storefront | Not connected in this registry |
| Gumroad | Digital downloads | Candidate; unverified |
| itch.io | Game-related downloads | Candidate; unverified |
| CGTrader | 3D models | Candidate; unverified |
| Etsy | Digital downloads | Later-stage candidate; unverified |
| Fab | Game-ready assets | Later-stage candidate; unverified |
| Unity Asset Store | Unity assets | Later-stage candidate; unverified |

These labels describe the company's intended channel strategy, not verified platform API support, seller eligibility, payout eligibility, fees, or automation access.

## Safety contract

- Every channel starts disconnected and unverified.
- Every external capability is reported as unverified; no adapter claims a feature merely because a platform is listed.
- No marketplace credentials or payout details are stored in this registry.
- No external API client, listing publication, listing update, order polling, refund, customer message, or payment operation is implemented here.
- Listing drafts are private internal records and cannot publish themselves.
- Business-unit filtering is explicit. The initial owned WooCommerce storefront is associated with physical-brand and digital-products; third-party marketplace candidates are associated with digital-products.
- Unsupported or unverified channel operations must remain manual and be described as such.

## API

- GET /storefronts/channels — owner-authenticated channel registry.
- GET /storefronts/channels?business_id=digital-products — filter by commercial business.
- GET /storefronts/channels/{channel_id} — owner-authenticated channel detail.

All responses state that external writes are disabled.

## Remaining work

1. Verify each platform's official API, seller eligibility, country/payout route, KYC, fees, and current terms.
2. Add persistent canonical product-to-channel mappings and draft listing records.
3. Add a WooCommerce read-only adapter and owner-approved account connection.
4. Add idempotent order-event ingestion and channel-scoped audit records.
5. Implement digital delivery/entitlement tracking only after order-state semantics are verified.
6. Add separate approval grants for every external write capability; no global write switch.
7. Add channel health, fee/revenue, and payout reconciliation views.
8. Run authenticated end-to-end acceptance tests before enabling any production connection.

No marketplace is enabled by this foundation, and no account or live listing is changed.
