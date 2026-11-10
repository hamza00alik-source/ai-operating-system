# AIOS External Integration Setup Guide

Updated: 2026-11-10

This guide records the account-side setup still required to activate external integrations. Credentials must be entered only in the AIOS Owner Dashboard or Railway Variables, never pasted into chat, GitHub issues, source code, or logs.

## Production API

- Railway service: `aios-api`
- Public API origin: `https://aios-api-production-e878.up.railway.app`
- Owner-protected integration endpoints require an authenticated Owner Dashboard session.

## Existing supported connection checks

### WordPress

1. Enable WordPress Application Passwords for the intended site user.
2. In the Owner Dashboard, choose the correct business environment and WordPress.
3. Supply the HTTPS site origin, WordPress username, and application password.
4. AIOS checks the authenticated `/wp-json/wp/v2/users/me?context=edit` endpoint.
5. The credential is encrypted in the AIOS vault.

Current capability: authenticated REST read access. Content creation, editing, publishing and plugin administration are not enabled by this verifier.

### WooCommerce

1. In WordPress, create WooCommerce REST API credentials for a dedicated integration user.
2. Use the narrowest available read-only permissions for initial connection.
3. In the Owner Dashboard, supply the HTTPS site origin, consumer key and consumer secret.
4. AIOS checks `/wp-json/wc/v3/products?per_page=1`.
5. The credential is encrypted in the business-specific vault.

Current capability: read-only product endpoint verification. Product changes, orders, refunds, customer data exports and store settings are not enabled by this verifier.

### PlayerAuctions

Use the PlayerAuctions seller API key and API secret in the Owner Dashboard for the intended business environment. AIOS performs a signed GET request for one offer. It does not create or update offers, change prices, inventory, orders or listings.

### Etsy

Etsy OAuth is implemented with the `shops_r` read scope. Configure the app values below, then initiate OAuth from the Owner Dashboard.

## Social OAuth app configuration

Create developer apps under the account owner’s control. Register the exact callback URI shown below, including HTTPS and path. Do not append query strings or fragments.

| Provider | Railway environment variables | Exact callback URI |
|---|---|---|
| Meta (Facebook Pages / linked Instagram professional accounts) | `AI_OS_OAUTH_META_CLIENT_ID`, `AI_OS_OAUTH_META_CLIENT_SECRET`, `AI_OS_OAUTH_META_REDIRECT_URI` | `https://aios-api-production-e878.up.railway.app/business-integrations/social/meta/callback` |
| TikTok | `AI_OS_OAUTH_TIKTOK_CLIENT_KEY`, `AI_OS_OAUTH_TIKTOK_CLIENT_SECRET`, `AI_OS_OAUTH_TIKTOK_REDIRECT_URI` | `https://aios-api-production-e878.up.railway.app/business-integrations/social/tiktok/callback` |
| YouTube / Google | `AI_OS_OAUTH_GOOGLE_CLIENT_ID`, `AI_OS_OAUTH_GOOGLE_CLIENT_SECRET`, `AI_OS_OAUTH_GOOGLE_REDIRECT_URI` | `https://aios-api-production-e878.up.railway.app/business-integrations/social/youtube/callback` |
| Pinterest | `AI_OS_OAUTH_PINTEREST_CLIENT_ID`, `AI_OS_OAUTH_PINTEREST_CLIENT_SECRET`, `AI_OS_OAUTH_PINTEREST_REDIRECT_URI` | `https://aios-api-production-e878.up.railway.app/business-integrations/social/pinterest/callback` |
| Reddit | `AI_OS_OAUTH_REDDIT_CLIENT_ID`, `AI_OS_OAUTH_REDDIT_CLIENT_SECRET`, `AI_OS_OAUTH_REDDIT_REDIRECT_URI` | `https://aios-api-production-e878.up.railway.app/business-integrations/social/reddit/callback` |
| Etsy | `AI_OS_OAUTH_ETSY_CLIENT_ID`, `AI_OS_OAUTH_ETSY_SHARED_SECRET`, `AI_OS_OAUTH_ETSY_REDIRECT_URI` | `https://aios-api-production-e878.up.railway.app/business-integrations/social/etsy/callback` |
| X | `AI_OS_OAUTH_X_CLIENT_ID`, `AI_OS_OAUTH_X_CLIENT_SECRET`, `AI_OS_OAUTH_X_REDIRECT_URI` | `https://aios-api-production-e878.up.railway.app/business-integrations/social/x/callback` |

The current social OAuth adapter requests read-oriented scopes only: account identity, page/channel/profile information and read access to existing content. It does not publish posts, reply to messages, send DMs, upload videos, or create campaigns. Some providers require app review, business verification or approved use cases before granting these scopes.

Set each provider's redirect variable to the exact URI in the table. Keep app secrets in Railway Variables. Once configured, open the Owner Dashboard, select the intended business environment, and initiate the provider connection. The OAuth callback stores the token encrypted.

## AI code evolution

The guarded code-evolution feature is deployed. Its feature flag is set to `AI_OS_CODE_EVOLUTION_ENABLED=true`, but code writing remains fail-closed until the GitHub token is configured.

Create a fine-grained GitHub personal access token restricted to `hamza00alik-source/ai-operating-system` with:
- Contents: Read and write
- Pull requests: Read and write
- Metadata: Read-only (normally granted automatically)

Add it in Railway production Variables as `AI_OS_GITHUB_TOKEN`. Do not paste the token into ChatGPT, source files, GitHub issues, or documentation. Do not grant administration, workflow, organization, or unrelated repository permissions.

The deployed API then reports readiness at the owner-only `GET /code-evolution/status` endpoint. Proposals are written only to isolated branches and draft PRs. The system does not merge or deploy its own changes.

## Background worker

The embedded worker configuration is `AI_OS_EMBEDDED_WORKER=true`. Keep the Railway API service at one replica while SQLite is the active queue database and retain its persistent volume. The worker suite handles bounded agent execution, internal inbox supervision, executive supervision and periodic brain learning. Do not scale this SQLite-backed service horizontally.

## Model provider requirement

The AIOS runtime will not spend money or silently fall back to paid inference. Configure at least one provider/model that has been checked against current provider terms, regional availability and zero-cost quota. The selected model must be explicitly confirmed free in the Owner Dashboard. A provider credential is not evidence that its model is free.

## Integrations not yet implemented for live operations

The credential vault has provider labels for Shopify, Stripe and PayPal, but that does not mean their OAuth/API workflows are complete. Dedicated connection verification and least-privilege scopes must be implemented and tested before using them. Payment integrations must remain read-only for payment-status verification; AIOS must not initiate charges, payouts, refunds or transfers.

Social publishing, marketplace listing creation, customer messaging, email sending and order fulfilment also require separate write adapters, permission review, test accounts and explicit owner approval. Do not treat a successful read-only OAuth connection as authorization for these actions.

## Database migration gate

The Supabase schema is installed and RLS is enabled on all 22 tables. The live Railway app still uses its existing configured database until the owner-authenticated Supabase `SELECT 1` probe succeeds and the existing SQLite volume is backed up, migrated and rollback-tested. Do not switch the production database before those checks.
