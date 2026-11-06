# AI Operating System

A modular, human-supervised foundation for running an AI-powered company, with the complete pinned Agency Agents specialist library (283 profiles across 18 divisions).

> Early development: the repository now includes a model-backed specialist worker runtime, but it is disabled by default and requires an explicitly configured compatible model endpoint. It is not a fully autonomous company; ecommerce, social integrations, and external actions remain disconnected.

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
# Configure a strong owner token before opening the dashboard.
export AI_OS_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf 'Owner token: %s\n' "$AI_OS_API_TOKEN"
uvicorn ai_os.api:app --reload
```

Open http://127.0.0.1:8000/docs.

Open the responsive owner dashboard at http://127.0.0.1:8000/dashboard. See [docs/OWNER_DASHBOARD.md](docs/OWNER_DASHBOARD.md) for dashboard behavior, data definitions, security, and limitations. Enter the configured `AI_OS_API_TOKEN`; the dashboard reads agent, run, job, approval, runtime, and audit data from the protected API. The dashboard shell itself is public, but its data APIs still require owner authentication.

## Current capabilities
- Create and list work tasks. The signed CEO approval ingress (`POST /ceo/approval-requests`) creates exact-scope requests; the owner-only inbox and decision API expose one-time approve/reject controls. Approval does not execute an external action.
- Discover all imported specialists with `GET /agents` (CEO plus 283 Agency Agents profiles).
- Read a specialist's complete source instructions with `GET /agents/{agent_id}/profile`.
- Discover the pinned scenario team runbooks with `GET /runbooks` and `GET /runbooks/{slug}`.
- Generate role-specific work packets that include the complete specialist profile, any active owner-approved versioned instruction addendum, and CEO reporting rules.
- Create deterministic plans with `POST /plans`.
- Check free-first execution settings with `GET /runtime`.
- Generate ready-to-paste agent prompts with `POST /work-packets`; this makes no model/API call.
- Execute dependency-ready specialist steps through a durable worker queue when an owner-configured model endpoint is explicitly enabled.
- Run a persistent worker process with `python -m ai_os.worker_service`; see [docs/RUNNING_AGENTS.md](docs/RUNNING_AGENTS.md).
- Persist task, company-run, report, queue, knowledge, and evaluation records in SQLite.
- Inspect per-agent evaluation history and cautious sample-gated quality trends.
- Draft evidence-linked CEO improvement proposals; owner approval is required for testing, followed by a separate explicit owner-token activation action.
- Run static instruction-contract checks and optional local-only baseline-vs-candidate behavior regression tests for owner-approved proposals, then explicitly activate the exact passing addendum through the owner dashboard; activation is versioned, audited, and rollback-capable. No remote model endpoint or API key is allowed for behavior testing.

See [docs/FREE_FIRST_EXECUTION.md](docs/FREE_FIRST_EXECUTION.md) for the no-API workflow, [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) for registry and planning, [docs/AGENCY_AGENTS_ADOPTION.md](docs/AGENCY_AGENTS_ADOPTION.md) for source adoption, [docs/INSTRUCTION_VERSIONING.md](docs/INSTRUCTION_VERSIONING.md) for controlled improvement and rollback, [docs/BEHAVIOR_TESTING.md](docs/BEHAVIOR_TESTING.md) for optional local regression tests, [docs/OWN_MODEL_STRATEGY.md](docs/OWN_MODEL_STRATEGY.md) for the company-owned model plan, and [docs/ROADMAP.md](docs/ROADMAP.md) for the implementation sequence.

Approval is a server-enforced workflow, not an execution sandbox. No external adapter currently consumes approvals to publish, message customers, spend, deploy, or change production. Keep production integrations disconnected until a separately reviewed execution adapter is implemented.


## Optional model-backed specialist and CEO execution

- Provider-neutral OpenAI-compatible chat-completions adapter plus an optional owner-configured local CLI backend; neither is selected by default.
- Model execution is disabled by default. The HTTP backend requires `AI_OS_MODEL_ENABLED=true`, `AI_OS_MODEL_BASE_URL`, and `AI_OS_MODEL_NAME`; the optional CLI backend requires `AI_OS_MODEL_BACKEND=command`, an executable, and a JSON argv template.
- Remote HTTP endpoints must use HTTPS; localhost model servers may use HTTP. API keys are read only from environment variables. CLI execution uses `shell=False` but inherits the CLI's own permissions; verify a prompt-only/no-tools CLI profile and set `AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED=true` before enabling it. See [docs/RUNNING_AGENTS.md](docs/RUNNING_AGENTS.md).
- `GET /models/status` checks readiness without contacting a provider.
- `POST /worker/run-once` schedules ready company-run steps and executes one durable job; the persistent worker uses the same queue.
- `python -m ai_os.worker_service` runs a separate polling worker process. It refuses to start unless model execution is enabled and configured.
- Specialists receive their full role profile, execute one bounded internal task through the configured model, and submit authenticated reports to the CEO in dependency order.
- `POST /ceo/review/{run_id}` sends completed specialist reports to the configured model and stores its structured CEO review. It performs no actions.
- Reports are treated as untrusted input. Recommendations cannot dispatch agents, create approvals, publish, spend, or contact customers.
- Free-tier quotas, privacy, retention, and terms vary. No provider is enabled by default.


### Company knowledge and research provenance

Source-attributed research can be stored as a candidate, reviewed by the owner,
and retained with its source metadata and audit history. The API does not
automatically verify sources or promote agent output to trusted knowledge.
See [docs/KNOWLEDGE_STORE.md](docs/KNOWLEDGE_STORE.md).


## SQLite backups

The project includes a local SQLite snapshot helper. It uses SQLite's online backup API, verifies the snapshot with `PRAGMA integrity_check`, checks core application tables, verifies the SHA-256 audit chain, and atomically replaces the destination file only after verification.

Example from the repository root:

```bash
python -c "from ai_os.db_backup import create_database_backup; print(create_database_backup('./backups/ai-os.sqlite3'))"
```

Keep backups outside the live database path and protect them as sensitive company data. Copy verified backups to a separate, access-controlled location. The helper does not upload, encrypt, schedule, or retain backups automatically. Do not restore or replace a live database while application workers are active.
