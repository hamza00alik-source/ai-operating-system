# OpenCompany AIOS

**One product. One codebase. One owner-governed company operating system.**

OpenCompany is the product and company identity; AIOS is its intelligence and execution engine. The independent implementation lives in `src/opencompany_app` and `src/opencompany_core`. The legacy `src/ai_os` package is historical reference material only and is not part of the new runtime.

## Current architecture

- FastAPI application and owner console in `src/opencompany_app`.
- Shared domain, orchestration, persistence and model-gateway services in `src/opencompany_core`.
- Persistent SQLite state, audit records, owner sessions, encrypted provider credentials, work queues and review-required deliverables.
- Ten department managers, 500 specialist role contracts and one executive orchestrator (511 role contracts). Role contracts are definitions, not 511 continuously running agents; role procedures share a generator/template and are being deepened over time.
- Four business-unit scopes: core, physical-products agency, own physical-product brand and digital products. Keep business records, work and credentials isolated by unit.
- Company-wide venture discovery can evaluate additional legitimate business opportunities without hard-coding the company to a fixed set of businesses.

The system is an independent platform foundation, not yet a fully autonomous or production-proven company. External store, marketplace, payment, social publishing, customer-support and fulfilment workflows remain incomplete or require dedicated integrations. Do not describe these as operational until implemented and verified.

## Development branch and production boundary

The active development line is `feature/opencompany-aios-unification`. It is not the production deployment. The current `vercel.json` routing still targets the legacy Railway service. Do not merge, change production routing, migrate production data or deploy this branch without a separate owner-approved cutover plan and verified rollback.

## Local setup

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export OPENCOMPANY_OWNER_API_KEY="replace-with-a-long-random-secret"
export OPENCOMPANY_SECRET_ENCRYPTION_KEY="replace-with-a-separate-random-secret-of-at-least-32-characters"
export OPENCOMPANY_COOKIE_SECURE="false"  # local HTTP development only
python main.py
```

Open the owner console at http://127.0.0.1:8000/owner and API docs at http://127.0.0.1:8000/docs. Use HTTPS and set `OPENCOMPANY_COOKIE_SECURE=true` in hosted environments. See `.env.example` for the supported starter variables.

## Persistence and deployment notes

- Set `OPENCOMPANY_DATABASE_PATH=/data/opencompany_core.sqlite3` and mount a persistent volume at `/data` on Railway.
- Keep owner keys, encryption keys, provider credentials and GitHub tokens in the host's secret manager. Never commit secrets.
- Back up the encryption key separately and securely; losing it can make encrypted provider credentials unrecoverable.
- The worker fleet is designed for one API process and one persistent SQLite volume. Do not run multiple hosts against the same SQLite file.
- Worker autostart is opt-in via `OPENCOMPANY_WORKER_AUTOSTART=true`. Work execution remains gated by owner-approved profiles, delegation and queue admission.
- The owner can export a consistent SQLite backup. Off-host retention and a rehearsed restore process remain operational requirements.

## Model-provider safety

OpenCompany's intended policy is fail-closed, zero-cost-only inference. A model ID that looks free is not sufficient evidence by itself. Eligibility must be confirmed from provider-reported pricing and current account access; non-zero or unknown costs must not silently pass. No paid fallback, automatic billing upgrade or spending is authorized. Use synthetic, non-sensitive input for an initial owner-approved live test.

UnoRouter is implemented as an optional provider in the independent runtime. Review current provider terms, privacy, data handling, account eligibility and pricing before sending company or customer data.

## Owner approval boundaries

The system must require explicit owner approval before spending, publishing, customer commitments, external account changes, financial actions, production changes or other consequential external side effects. Research, drafting and internal planning do not grant permission to take those actions.

## Legacy and provenance policy

- `src/ai_os` and historical Agency Agents manifests are quarantined reference material, not runtime dependencies or an architectural foundation.
- Do not copy legacy runtime code into OpenCompany. Use external projects only as optional research references; implement OpenCompany's own architecture and workflows.
- Legacy tests that import `ai_os` must remain separate from the independent OpenCompany test suite.
- See [the quarantine and provenance register](docs/QUARANTINE_REGISTER.md) for the current boundary and audit limitations.

## Current roadmap

Priority gaps include stronger role-based owner/operator permissions, workflow cancellation and resume, per-attempt diagnostics, multi-host coordination, knowledge-library access controls and retention, evaluation benchmarks, WooCommerce and social integrations, customer support, payment verification, marketplace/fulfilment sync, off-host backup/restore rehearsal, monitoring and incident runbooks, beginner recovery documentation, and full mobile-browser acceptance.

See [docs/ROADMAP.md](docs/ROADMAP.md), [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md), [docs/COMPANY_STRUCTURE.md](docs/COMPANY_STRUCTURE.md), and [docs/VENTURE_PORTFOLIO.md](docs/VENTURE_PORTFOLIO.md).

## Quality and release status

Do not claim tests passed unless they have actually been run. The owner has deferred CI/testing until 2026-12-01; until then, make only explicitly approved source/documentation changes and report verification limits accurately. A successful local check is not production acceptance.
