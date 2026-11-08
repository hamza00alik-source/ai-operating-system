# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this repository is a workflow and coordination foundation, not yet a fully autonomous company. Agent registration, durable task claiming, shared memory, audit events, task/approval APIs and SQLite persistence are implemented. Live LLM execution, production worker orchestration, ecommerce, social and customer integrations are not yet connected.

## Principles
- Human approval before external or consequential actions.
- No spending, publishing, customer commitments, or production changes without explicit approval.
- Provider-independent architecture; no mandatory proprietary model vendor.
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

## Current capabilities
- Create and list work tasks.
- Register and list agents.
- Atomically claim queued tasks for registered agents.
- Store and search shared memory entries with source and author metadata.
- Read a durable audit-event history for agent registration, task claims and memory writes.
- Create, list, approve, and reject approval requests.
- Persist records in SQLite with backward-compatible task-table migration.
- Health endpoint and API-key protection for operational endpoints outside development.

The coordination endpoints provide durable handoff primitives; they do not themselves run an LLM or prove that an agent completed the work. Model execution and supervised worker orchestration are separate implementation phases.

## API overview
- `POST /tasks`, `GET /tasks`
- `POST /agents/register`, `GET /agents`
- `POST /agents/{agent_id}/claim`
- `POST /memory`, `GET /memory?q=...`
- `GET /audit`
- `POST /approvals`, `GET /approvals`
- `POST /approvals/{approval_id}/decision`
- `GET /health`

In development, operational endpoints are open for local testing. In staging/production, set `AI_OS_ENV=production` and a strong private `AI_OS_API_KEY`. Send it in the `X-API-Key` header. The app refuses to start in non-development mode if the key is missing. Keep `/health` public for uptime checks.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authorization, audit logging, and integration safeguards are reviewed.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).
