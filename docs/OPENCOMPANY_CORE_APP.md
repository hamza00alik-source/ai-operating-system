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
- `GET /workforce/roles` — returns the original OpenCompany capability specifications.
- `GET /organization/departments` — returns the ten independently designed department contracts.
- `GET /media/capabilities` — reports video-production capability state; LongCat-Video remains researched, not connected.
- `GET /providers/candidates` — lists candidate free-model routes and activation gates.
- `GET /providers/status` — reports whether the explicit OpenRouter free-model configuration is present, without exposing credentials.
- `POST /plans/preview` — validates a proposed dependency graph and reports ready or blocked work. It does not enqueue or execute tasks.
- `GET /policy/protected-actions` — lists actions that require explicit owner approval.

Owner-authenticated endpoints require `X-OpenCompany-API-Key`:
- `GET /work-items` — lists persisted work items.
- `POST /work-items` — creates a work item in the draft state.
- `POST /work-items/{id}/transition` — validates and records a permitted state transition.
- `GET /audit/verify` — checks the integrity of the local audit hash chain.

The organization registry validates department-to-role assignments and publishes each department's accountabilities, manager role, decision scope, measures, and approval boundaries. The current workforce contains ten original specialist/manager role definitions; department manager role keys are assignments, not proof that ten continuously running agents exist.

The core library also includes a provider-neutral model gateway and a bounded specialist executor. No provider is enabled by default. OpenRouter free variants, Groq, and Cloudflare Workers AI are recorded as candidates only; account eligibility, exact model pricing, credentials, and zero-cost inference have not been verified. A provider can be called only when its configuration explicitly confirms free access or carries a separate owner-approved spending ceiling. The executor produces draft text deliverables only; it has no tools or authority to perform external actions.

Work-item changes and their audit records are committed together in a database transaction. The audit chain is tamper-evident; it is not a substitute for access control, backups, or independent log retention.

## Deliberate limitations

LongCat-Video is registered as a Media & Creative Production capability, but is not installed, connected, or active. Its local execution requires a CUDA-capable GPU, model dependencies, and downloaded weights. No paid or metered video generation is enabled.

This is an early operational foundation, not a production autonomous agent service. It has no model calls, browser, shell, payments, marketplace publishing, customer messaging, or automatic code modification. It does not perform external business actions.

The improvement module records evidence-based proposals. An owner decision is required before a proposal can be marked approved; approval does not automatically modify source code.

## Production readiness blockers

Do not point production deployment at this application yet. Before production use, complete:
- Strong owner identity and session management beyond a single shared API key.
- Rate limiting, HTTPS enforcement, secret rotation, and security review.
- Durable storage backups, restore drills, retention, and audit export.
- Worker lifecycle, concurrency control, leases, retries, and recovery.
- A separately reviewed and explicitly configured model adapter; no OpenAI or other live provider is enabled by default.
- Tool permission boundaries and per-action approval enforcement.
- Integration testing, migration/rollback plans, and operational monitoring.
- Provenance and licence audit of the remaining legacy repository.

The existing deployment configuration remains unchanged while the independent service is developed and verified.
