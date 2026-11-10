# Standalone OpenCompany Core Application

The clean-room rebuild introduces a separate application package at `src/opencompany_app`. It does not import the legacy `src/ai_os` application.

## Local development

Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn opencompany_app.api:app --reload
```

## Current endpoints

- `GET /health` — confirms the service is alive and in read-only mode.
- `GET /workforce/roles` — returns the nine original OpenCompany capability specifications.
- `POST /plans/preview` — validates a proposed dependency graph and reports ready or blocked work. It does not enqueue or execute tasks.
- `GET /policy/protected-actions` — lists actions that require explicit owner approval.

This is a foundation, not a production autonomous agent service. It has no model calls, persistent storage, credentials, browser, shell, payments, marketplace publishing, or external side effects.

## Release status

Do not point production deployment at this application yet. Authentication, persistent storage, audit-event persistence, worker lifecycle, operational monitoring, integration permissions, and migration/rollback plans are still required. The existing deployment configuration remains unchanged while the independent service is developed and verified.
