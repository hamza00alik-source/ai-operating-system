# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this repository is a starter foundation, not a fully autonomous company. A guarded model adapter and provider catalogue are implemented, but no provider is configured by default. Durable background agents, ecommerce, and social integrations are not connected yet.

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

In development, operational endpoints are open for local testing. In staging/production, set `AI_OS_ENV=production` and a strong private `AI_OS_API_KEY`. Send it in the `X-API-Key` header. The app refuses to start in non-development mode if the key is missing. Keep `/health` public for uptime checks.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authorization, audit logging, and integration safeguards are reviewed.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Optional model connectivity (disabled by default)

AIOS includes a provider-neutral OpenAI-compatible chat adapter and a small provider discovery catalogue. It does not include API keys and does not assume that a provider's free tier is permanent. All model calls are disabled unless `AI_OS_MODEL_ENABLED=true` is explicitly set.

Configure the endpoint and model using private environment variables:
- `AI_OS_MODEL_PROVIDER`
- `AI_OS_MODEL_BASE_URL`
- `AI_OS_MODEL_NAME`
- `AI_OS_MODEL_API_KEY` (optional only for documented keyless endpoints)
- `AI_OS_MODEL_TIMEOUT_SECONDS`
- `AI_OS_MODEL_MAX_TOKENS`

The protected `GET /models/status` endpoint reports configuration without revealing secrets. `GET /models/providers` lists discovery metadata and does not contact providers. `POST /models/test` makes one request only when model calls are enabled. No paid-provider fallback or automatic account rotation is implemented.

Example local test request (after configuring a legitimate endpoint and enabling it):

```bash
curl -X POST http://127.0.0.1:8000/models/test \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Reply with the word READY."}'
```

For production, also provide the normal `X-API-Key` header. A successful adapter test proves connectivity for that configured endpoint only; it does not certify that all providers in the catalogue are free or available.

## Durable task worker (first execution milestone)

The repository now contains a lease-based SQLite worker:
- `src/ai_os/worker.py` claims one queued task transactionally, invokes the explicitly configured model, and persists the result.
- `src/ai_os/agent_runtime.py` recovers expired worker leases after a process crash/restart and marks tasks failed after their retry limit.
- `src/ai_os/worker_service.py` supervises the worker, applies bounded backoff, and handles SIGINT/SIGTERM.
- Task responses include result, error, and attempt count.

The worker is a task executor, not yet a multi-agent team. It does not publish, spend money, contact customers, deploy, or execute MCP tools. It refuses to start unless the model adapter is fully configured and enabled.

Run it in a separate process after setting the same database and approved model environment variables as the API:

```bash
python -m ai_os.worker_service
```

For a real run, ensure the API and worker share a persistent SQLite file and that the selected provider's current terms, quotas, and commercial-use rules have been reviewed.
