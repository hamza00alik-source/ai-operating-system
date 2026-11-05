# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this is not yet a fully autonomous company. The registry, planning API, and no-API manual work-packet mode are available. Model execution, background workers, ecommerce, and social integrations are not connected.

## Principles
- Free-first: no paid model API is required for the current workflow.
- Human approval before external or consequential actions.
- No spending, publishing, customer commitments, or production changes without explicit approval.
- Provider-independent architecture; no silent paid fallback.
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
- Create and list work tasks and approval requests.
- Discover enabled specialists with `GET /agents`.
- Create deterministic plans with `POST /plans`.
- Check free-first execution settings with `GET /runtime`.
- Generate ready-to-paste agent prompts with `POST /work-packets`; this makes no model/API call.
- Persist task and approval records in SQLite.

See [docs/FREE_FIRST_EXECUTION.md](docs/FREE_FIRST_EXECUTION.md) for the no-API workflow, [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) for registry and planning, [docs/AGENCY_AGENTS_ADOPTION.md](docs/AGENCY_AGENTS_ADOPTION.md) for source adoption, and [docs/ROADMAP.md](docs/ROADMAP.md) for the implementation sequence.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authentication, authorization, audit logging, and integration safeguards exist.
