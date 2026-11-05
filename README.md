# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this repository is not yet a fully autonomous company. The agent registry and deterministic planning API are available; model execution, background workers, ecommerce, and social integrations are not connected yet.

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

## Current capabilities
- Create and list work tasks.
- Create, list, approve, and reject approval requests.
- Discover enabled specialists with `GET /agents`.
- Create a deterministic, non-executing work plan with `POST /plans`.
- Persist task and approval records in SQLite.
- Health endpoint.

See [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) for the agent registry and planning API, [docs/AGENCY_AGENTS_ADOPTION.md](docs/AGENCY_AGENTS_ADOPTION.md) for upstream adoption strategy, and [docs/ROADMAP.md](docs/ROADMAP.md) for the implementation sequence.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authentication, authorization, audit logging, and integration safeguards exist.
