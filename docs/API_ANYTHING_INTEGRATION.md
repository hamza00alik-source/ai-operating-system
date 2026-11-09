# API Anything integration

This repository integrates [goodnight000/api-anything](https://github.com/goodnight000/api-anything)
as an optional website-to-API layer. It does not replace UnoRouter, the LLM gateway, or the
existing research-source capture pipeline.

## Architecture

- The AI Operating System remains the owner console and policy boundary.
- Run API Anything as a separate Node.js 22.13+ service (for example, a private Railway service).
- Keep that service private to the Railway project/network. Do not expose it to the public internet.
- The Python Railway API calls its HTTP interface using a private URL and bearer token.
- The Vercel dashboard talks only to the existing authenticated AI OS API; it never receives the
  API Anything token.
- Website calls use only `POST /v1/call/{site}/{operation}`, never `/v1/write`.
- Every bridge call is forced to `maxTier: 1` (plain HTTP only). Browser fallbacks are not enabled.

## Railway variables

Set these as private variables on the AI OS backend service after the separate API Anything
service is deployed:

| Variable | Value |
|---|---|
| `AI_OS_API_ANYTHING_URL` | Private HTTP(S) origin of the API Anything service, without a path |
| `AI_OS_API_ANYTHING_TOKEN` | The API Anything service's bearer token |

Generate a strong random token in the API Anything service. Start it with writes disabled and
learning hidden until owner-led testing is complete:

```sh
API_ANYTHING_TOKEN=<strong-random-token> npx -y api-anything serve --no-learn
```

Do not put the token in GitHub, the Vercel frontend, a browser, logs, or chat. Do not enable
`--allow-writes`. Prefer a separate, minimal `API_ANYTHING_HOME` containing only approved
public read operations. Do not import personal browser cookies or signed-in sessions.

## Owner-only API endpoints

All endpoints below require the AI OS owner session or `X-API-Key`:

- `GET /integrations/api-anything/status` — connection status, never secrets.
- `GET /integrations/api-anything/sites` — list installed sites and operations.
- `GET /integrations/api-anything/find?q=...` — search the installed/shared catalog.
- `POST /integrations/api-anything/call/{site}/{operation}` — execute one read operation.

Example call body:

```json
{"args":{"query":"sqlite"},"fields":["title","points"]}
```

Calls are limited to a 20 KB argument object, 1 MB response, 25-second timeout, same-origin
redirects, and tier 1. The API OS does not provide a write endpoint. The owner-only boundary is
intentional: agent-initiated calls, learning, authenticated sites, and any write capability are
not enabled by this first integration.

## Current deployment status

Code integration alone does not provision the separate Node service or configure Railway secrets.
After code review, deploy the API Anything service privately, set the two variables above, and
verify the status endpoint. No production merge or deployment is performed by this change.
