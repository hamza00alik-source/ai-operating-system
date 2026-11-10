# API Anything integration and platform account connections

## Correct runtime model

API Anything is a Node.js service. Its supported hosted interface is `api-anything serve`:
- REST operations under `/v1`
- MCP over Streamable HTTP at `/mcp`
- OpenAPI at `/openapi.json`

It is not a generic OAuth broker and does not provide a REST `/v1/login` endpoint. Its `login` tool is an MCP/CLI operation that imports cookies from a browser profile on the machine running API Anything, or opens a local browser window. Therefore a hosted Railway service cannot silently log the owner into a site using cookies from the owner's Android browser. Do not invent a login endpoint or ask the owner to paste passwords/cookies into chat.

## Deployment

Run API Anything as a separate private Node.js 22.13+ service in the same Railway project/network as the AIOS API. Use a persistent volume for `API_ANYTHING_HOME` so installed site specs and any explicitly authorized sessions survive restarts.

Service start command:

```sh
npx -y api-anything serve --host 0.0.0.0 --no-learn
```

Set private variables on the API Anything service:
- `API_ANYTHING_TOKEN`: strong random bearer token
- `API_ANYTHING_HOME`: persistent mounted directory for API Anything state

Keep the service private to the Railway project. Do not expose its port publicly. Do not use `--allow-writes`. If browser-based login is ever deliberately enabled, it must be a separate owner-approved setup with an interactive browser on the runtime host; it is not available as a dashboard one-click login in this hosted topology.

Set these private variables on the AIOS API service:
- `AI_OS_API_ANYTHING_URL`: private origin of the API Anything service, e.g. `http://api-anything.railway.internal:8787`
- `AI_OS_API_ANYTHING_TOKEN`: the same bearer token

Never put the token in GitHub, the Vercel frontend, browser JavaScript, logs, or chat.

## Current Railway audit (2026-11-10)

The Railway project already contains live `api-anything` and `aios-api` services. The API Anything service is configured with `node dist/cli.js serve --host 0.0.0.0 --port $PORT --no-learn --public-url http://api-anything.railway.internal:$PORT`; it has no public domain. The API Anything bearer-token variable is present on that service, and the AIOS API has both `AI_OS_API_ANYTHING_URL` and `AI_OS_API_ANYTHING_TOKEN` variables. Railway logs show successful `GET /v1/health` checks and successful AIOS calls to `/integrations/api-anything/status`.

The API Anything service currently has **no attached persistent volume**. Its local site state and any future account sessions can therefore be lost on redeploy/restart. A dedicated volume would improve persistence but is not provisioned here because the owner requires a zero-budget setup and volume cost/allowance must be checked first. No public domain was added and no token values were read or changed during this audit.

## Owner dashboard capabilities

The dashboard calls only the AIOS authenticated API. AIOS keeps the API Anything token server-side.

- `GET /integrations/api-anything/status`: service health and configuration state.
- `GET /integrations/api-anything/sites`: installed sites.
- `GET /integrations/api-anything/sites/{site}`: installed operations for one site.
- `GET /integrations/api-anything/find?q=...`: local/shared catalog search.
- `POST /integrations/api-anything/call/{site}/{operation}`: owner-triggered read.

All website calls are forced to `maxTier=1`, limited to 20 KB arguments, 1 MB responses and 25-second timeouts. Cross-origin redirects are blocked. AIOS does not expose `/v1/write`, browser fallback, or unattended learning. The owner dashboard's generic API Anything panel is for discovering and running read operations, not account sign-in or publishing.

## WordPress and WooCommerce account connections

WordPress and WooCommerce are connected directly through their official REST APIs from the Business section of the owner dashboard, not by pretending API Anything is an OAuth provider.

- WordPress: use a dedicated WordPress user and an Application Password. Enter the HTTPS site origin, username and Application Password. AIOS verifies with `GET /wp-json/wp/v2/users/me?context=edit`.
- WooCommerce: create a dedicated REST API key with the minimum required permissions. Enter the HTTPS site origin, consumer key and consumer secret. AIOS verifies with `GET /wp-json/wc/v3/products?per_page=1`.

Successful credentials are encrypted at rest in the business-specific vault. The account connection is scoped to the selected business environment. Verification is read-only; it does not create or update posts, products, orders, inventory or settings. Do not use an administrator password where an Application Password or restricted API key is available.

## Social and marketplace accounts

Instagram, Facebook, TikTok, YouTube, Pinterest, Reddit and X, plus marketplace accounts, require their own supported OAuth/API adapter and provider-specific app registration, redirect URI, scopes and approval rules. API Anything can discover and call website operations, but it does not replace official platform OAuth or grant account access by itself. These providers must remain marked as not connected until their own authorization flow is implemented and a real account test succeeds.

Publishing, messaging, listing products, changing prices, fulfilling orders and financial actions remain disabled until a separate owner approval is recorded for the specific action. Connection tests alone never authorize these actions.

## Production verification

A source-code change is not a live connection. After the API Anything service and its private variables are provisioned, verify the dashboard status and read-only site discovery. Verify WordPress and WooCommerce separately from the Business section. No production merge or deployment is implied by a draft PR.


## Social OAuth account linking (implemented, awaiting owner app registration)

The Business dashboard now has server-side authorization-code flows for:
- Meta (Facebook Pages and linked Instagram professional accounts, one Meta app)
- TikTok
- YouTube (Google OAuth)
- Pinterest
- Reddit
- X (OAuth 2.0 with PKCE)

Only read-oriented scopes are requested by default. A successful callback verifies the returned account identity and stores the access token, optional refresh token, expiry and granted-scope metadata in the encrypted, business-scoped credential vault. OAuth state is random, single-use, expires after 15 minutes, and is bound to the selected business. X's PKCE verifier is encrypted at rest. No platform publishing, messaging, ad management, listing, purchasing or financial actions are implemented by these OAuth flows.

### Required server variables

Set these only in the AIOS API hosting environment (never GitHub, browser JavaScript or chat):

| Provider | Client ID / key | Client secret | Exact callback variable |
|---|---|---|---|
| Meta | `AI_OS_OAUTH_META_CLIENT_ID` | `AI_OS_OAUTH_META_CLIENT_SECRET` | `AI_OS_OAUTH_META_REDIRECT_URI` |
| TikTok | `AI_OS_OAUTH_TIKTOK_CLIENT_KEY` | `AI_OS_OAUTH_TIKTOK_CLIENT_SECRET` | `AI_OS_OAUTH_TIKTOK_REDIRECT_URI` |
| YouTube | `AI_OS_OAUTH_GOOGLE_CLIENT_ID` | `AI_OS_OAUTH_GOOGLE_CLIENT_SECRET` | `AI_OS_OAUTH_GOOGLE_REDIRECT_URI` |
| Pinterest | `AI_OS_OAUTH_PINTEREST_CLIENT_ID` | `AI_OS_OAUTH_PINTEREST_CLIENT_SECRET` | `AI_OS_OAUTH_PINTEREST_REDIRECT_URI` |
| Reddit | `AI_OS_OAUTH_REDDIT_CLIENT_ID` | `AI_OS_OAUTH_REDDIT_CLIENT_SECRET` | `AI_OS_OAUTH_REDDIT_REDIRECT_URI` |
| X | `AI_OS_OAUTH_X_CLIENT_ID` | `AI_OS_OAUTH_X_CLIENT_SECRET` | `AI_OS_OAUTH_X_REDIRECT_URI` |

Each redirect variable must be the exact HTTPS callback URL registered with that provider:
`https://YOUR-AIOS-API-HOST/business-integrations/social/{provider}/callback`
where provider is `meta`, `tiktok`, `youtube`, `pinterest`, `reddit`, or `x`. The public AIOS API origin must be known and registered before authorization can work. Keep `AI_OS_CREDENTIAL_ENCRYPTION_KEY` configured and backed up; losing it makes stored tokens unrecoverable.

App registration, provider review/approval, redirect URI registration, and environment-variable entry are owner-side prerequisites. Meta, TikTok, Pinterest, Google and X may restrict scopes/features until app review or production access is approved. Reddit external Data API access has its own approval and terms process; Devvit app login is not a substitute for credentials for an external AIOS integration. The dashboard reports each app as setup-required until all three variables exist; it does not pretend an account is connected. The OAuth status endpoint is owner-authenticated. Callback state is single-use and short-lived.

**Current limitation:** token refresh and provider-specific publishing endpoints are not yet implemented. An expired token must be re-authorized. Publishing stays out of scope until separate owner-approved action workflows and provider permission review are complete.

## Marketplace and digital storefront integrations

### Gaming marketplaces selected for AIOS

- **PlayerAuctions — read-only seller connection implemented.** The owner dashboard accepts the seller API key and secret. AIOS signs a GET request to the documented offer-list endpoint using HMAC-SHA256 and verifies the API response before saving credentials in the encrypted business vault. Only one offer page is sampled. No offer, price, inventory, image, order, delivery or cancellation endpoint is called. The API supports offer-management writes, so future write methods must remain behind explicit owner approval and a preview/diff. The published API has seller-level hourly quotas and a 5-second same-product creation cooldown; AIOS does not consume write quotas during connection checks.
- **Eldorado.gg — official Seller API exists, connector not enabled yet.** Verified sellers can generate Client ID/Client secret credentials. The API issues 15-minute access tokens and supports offer and order management. The provider states there is no test environment and API requests affect live offers/orders. The precise token request contract and read-only identity/offer endpoints must be verified from the full official API spec before implementation; do not guess. AIOS must keep all write methods disabled until a specific owner approval flow exists.
- **G2G — conditional eligibility blocker.** G2G OpenAPI access requires platform approval. Its published requirements currently say only business-account sellers located in Malaysia and Indonesia may apply. A Pakistan-based seller should not enter credentials or invest in this integration unless the actual seller entity meets G2G's current eligibility and receives approval.
- **Z2U — no public seller API contract verified.** No public official seller API authentication/specification was found in the research pass. The platform's own seller dashboard remains the official route until Z2U provides a documented seller API. Do not scrape or replay browser sessions.

### Digital storefronts selected for AIOS

- **Etsy — owner-shop OAuth connection implemented on this branch.** Uses the official Seller App OAuth 2.0 authorization-code flow with PKCE and the `shops_r` scope. The owner must register a Seller App, configure the API keystring, shared secret and exact HTTPS callback URL, then connect the shop from the dashboard. The API key/shared secret and OAuth tokens are encrypted in the business vault. The adapter verifies `/users/me` and the owner's shop with read-only requests. No listings or orders are changed. A Seller App is scoped to the owner's own shop; broader multi-seller access requires a different access path and review.
- **Gumroad — official API/MCP capabilities exist, but standard API product creation/file uploads are not available in the documented API.** The current official assistant connector supports read operations and product draft/edit/publish actions subject to granted scopes; this must be integrated through its official OAuth/MCP surface, not guessed API endpoints. Not connected yet.
- **itch.io — uploads use the official Butler CLI.** This is a worker/runtime integration rather than a browser OAuth login. It requires a persistent, securely configured worker and an owner-approved publish action; no upload has been triggered.
- **CGTrader — API access requires an application/request for an API key; the site documents OAuth 2.0 and inbound seller workflows for drafts, bulk model uploads and updates.** Access is not automatic. Not connected yet.
- **Fab — publisher workflow is documented through the creator portal, including listing creation, asset upload, review and publication.** No public seller API specification was identified in this research pass. Publishing remains a manual/owner-approved provider workflow; do not infer an API or automate browser sessions.

### Owner approval boundary

All marketplace account connection tests are read-only. Listing creation, editing, publishing, price/inventory changes, order delivery/cancellation, buyer messages, refunds and payout/financial actions remain unavailable unless a provider-specific method is implemented and the owner approves that specific external action. Marketplace terms, seller eligibility, account verification and fees must be reviewed before activation. The zero-budget requirement rules out paid API plans, seller-level upgrades, paid middleware and metered services without explicit owner approval.
