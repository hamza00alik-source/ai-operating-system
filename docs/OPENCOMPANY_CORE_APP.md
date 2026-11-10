# Standalone OpenCompany Core Application

The rebuild introduces a separate application package at `src/opencompany_app`. It does not import the legacy `src/ai_os` application.

## Local development

Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export OPENCOMPANY_OWNER_API_KEY="use-a-long-random-secret"
export OPENCOMPANY_DATABASE_PATH="data/opencompany_core.sqlite3"
uvicorn opencompany_app.api:app --reload
```

Never commit the owner API key. Supply it through a private environment-variable manager. The database path is configurable; keep the database on a persistent private volume for deployments.

## Current endpoints

Public, read-only endpoints:
- `GET /health` — confirms service availability.
- `GET /workforce/roles` — returns the nine original OpenCompany capability specifications.
- `POST /plans/preview` — validates a proposed dependency graph and reports ready or blocked work. It does not enqueue or execute tasks.
- `GET /policy/protected-actions` — lists actions that require explicit owner approval.

Owner-authenticated endpoints require `X-OpenCompany-API-Key`:
- `GET /work-items` — lists persisted work items.
- `POST /work-items` — creates a work item in the draft state.
- `POST /work-items/{id}/transition` — validates and records a permitted state transition.
- `GET /audit/verify` — checks the integrity of the local audit hash chain.

Work-item changes and their audit records are committed together in a database transaction. The audit chain is tamper-evident; it is not a substitute for access control, backups, or independent log retention.

## Deliberate limitations

This is an early operational foundation, not a production autonomous agent service. It has no model calls, browser, shell, payments, marketplace publishing, customer messaging, or automatic code modification. It does not perform external business actions.

The improvement module records evidence-based proposals. An owner decision is required before a proposal can be marked approved; approval does not automatically modify source code.

## Production readiness blockers

Do not point production deployment at this application yet. Before production use, complete:
- Strong owner identity and session management beyond a single shared API key.
- Rate limiting, HTTPS enforcement, secret rotation, and security review.
- Durable storage backups, restore drills, retention, and audit export.
- Worker lifecycle, concurrency control, leases, retries, and recovery.
- Tool permission boundaries and per-action approval enforcement.
- Integration testing, migration/rollback plans, and operational monitoring.
- Provenance and licence audit of the remaining legacy repository.

The existing deployment configuration remains unchanged while the independent service is developed and verified.
