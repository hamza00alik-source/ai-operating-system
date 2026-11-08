# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this repository is a starter foundation, not a fully autonomous company. The provider-neutral LLM connectivity layer is now implemented, but no external provider is connected until its endpoint, model, and secret are configured.

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

Open http://127.0.0.1:8000/docs.

## Current starter capabilities
- Create and list work tasks.
- Create, list, approve, and reject approval requests.
- Persist records in SQLite.
- Health endpoint.
- API-key protection for operational endpoints outside development.
- Configurable OpenAI-compatible LLM provider registry.
- Protected provider-status and live connectivity-test endpoints.
- Free-tier confirmation guard; paid API calls are blocked unless explicitly enabled by the owner.

In development, operational endpoints are open for local testing. In staging/production, set `AI_OS_ENV=production` and a strong private `AI_OS_API_KEY`. Send it in the `X-API-Key` header. The app refuses to start in non-development mode if the key is missing. Keep `/health` public for uptime checks.

See [docs/LLM_PROVIDERS.md](docs/LLM_PROVIDERS.md) before configuring a provider. A live test uses provider quota and may incur charges if the provider is not genuinely free; verify current pricing and terms first. Never commit API keys.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authorization, audit logging, and integration safeguards are reviewed.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).
