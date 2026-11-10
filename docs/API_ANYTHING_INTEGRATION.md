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
