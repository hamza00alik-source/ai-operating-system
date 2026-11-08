# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this is a supervised operating-system foundation, not a fully autonomous company. The GitHub discovery worker is implemented as an initial capability; general-purpose AI agent execution, ecommerce, and social integrations are not yet production-connected.

## Principles
- Human approval before external or consequential actions.
- No spending, publishing, customer commitments, or production changes without explicit approval.
- Provider-independent architecture.
- Local-first development; SQLite is the default.
- Never commit secrets or customer data.

## Quick start
Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn ai_os.api:app --reload
```

Open http://127.0.0.1:8000/owner for the visual owner console, or http://127.0.0.1:8000/docs for the API.

## Current starter capabilities
- Create and list work tasks.
- Create, list, approve, and reject approval requests.
- Persist records in SQLite.
- Health endpoint.
- API-key protection for operational endpoints outside development.

In development, operational endpoints are open for local testing. In staging/production, set `AI_OS_ENV=production` and a strong private `AI_OS_API_KEY`. Send it in the `X-API-Key` header. The app refuses to start in non-development mode if the key is missing. Keep `/health` public for uptime checks.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authorization, audit logging, and integration safeguards are reviewed.

## Supervised technology discovery (initial implementation)

The visual owner console at `/owner` can queue GitHub repository discovery scans and display persisted scan/candidate results. API endpoints are also available:

- `POST /discovery/scans` with `{"categories":["agent-frameworks","mcp-servers"]}`
- `GET /discovery/scans`
- `GET /discovery/candidates`

Run the separate discovery worker alongside the API (both processes must remain running):

```bash
python -m ai_os.discovery_worker
```

The worker searches public GitHub repository metadata. Set `GITHUB_TOKEN` as a private environment variable to use authenticated GitHub API limits; never commit it. Without a token, GitHub documents a lower unauthenticated limit. Scans are queued by the API and processed by the worker. This is a GitHub-metadata discovery MVP, not a complete vendor/API price, security, or commercial-terms audit. Those fields remain explicitly unverified. See [docs/RESEARCH_DISCOVERY_PIPELINE.md](docs/RESEARCH_DISCOVERY_PIPELINE.md).

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).


## Free-tier model gateway (initial integration)

The protected owner API now exposes a provider registry and a real inference test:

- `GET /models/providers` reports whether Groq, Google Gemini, and OpenRouter keys are configured. It never returns key values.
- `POST /models/test` makes one capped chat-completion request to the selected provider and returns the model response, latency, and provider-reported token usage.
- Supported environment variables: `GROQ_API_KEY`, `GEMINI_API_KEY`, and `OPENROUTER_API_KEY`.
- Suggested initial free-tier model IDs: `llama-3.3-70b-versatile`, `gemini-2.5-flash`, and `google/gemma-3-27b-it:free`. Model availability and free quotas can change; confirm against the provider's live model catalogue.
- This gateway makes no paid fallback, caps each test at 256 output tokens and 35 seconds, and does not persist prompts or responses.
- Provider keys are intentionally not accepted through the API or stored in SQLite. Configure them as private environment variables in the host. A provider marked `key-required` is not connected yet.
- The browser-only InBrowser/Pocket LLM path is not the same as a server-side API and is not included in this server gateway.

These providers offer free tiers, not unlimited inference. Free-tier terms, model availability, commercial-use permissions, and data handling must be checked before production/customer use. The gateway is an integration foundation; it does not claim that a provider is connected until a real test call succeeds.
