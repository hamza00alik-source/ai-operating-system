# AI Operating System

A modular, human-supervised foundation for running an AI-powered company, with the complete pinned Agency Agents specialist library (283 profiles across 18 divisions).

> Early development: the repository includes a model-backed specialist worker with Gemini, Groq, and local Ollama presets, but model execution remains disabled by default. Cloud inference requires a private API key and owner verification of free-tier eligibility; the worker also needs a persistent host and explicit approval. It is not a fully autonomous company; ecommerce, social integrations, and external actions remain disconnected.

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

Open the responsive owner dashboard at http://127.0.0.1:8000/dashboard. See [docs/OWNER_DASHBOARD.md](docs/OWNER_DASHBOARD.md) for dashboard behavior, data definitions, security, and limitations. Enter the configured `AI_OS_API_TOKEN`; the dashboard reads agent, run, job, approval, runtime, and audit data from the protected API. The deployment key may be supplied as `AI_OS_API_KEY` for compatibility; `AI_OS_API_TOKEN` takes precedence when both are set. The dashboard shell itself is public, but its data APIs still require owner authentication.

## Hosting preparation

A Python host entry point and deployment checklist are included. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). This is preparation only; it does not mean the service has been deployed. Configure a persistent SQLite path and owner API key before production use.

## Current capabilities
- Create and list work tasks. The signed CEO approval ingress (`POST /ceo/approval-requests`) creates exact-scope requests; the owner-only inbox and decision API expose one-time approve/reject controls. The internal action gateway can consume exact approvals for trusted adapters, but external execution is disabled and no production adapter is registered.
- Discover all imported specialists with `GET /agents` (CEO plus 283 Agency Agents profiles).
- Read a specialist's complete source instructions with `GET /agents/{agent_id}/profile`.
- Discover the pinned scenario team runbooks with `GET /runbooks` and `GET /runbooks/{slug}`.
- Generate role-specific work packets that include the complete specialist profile, any active owner-approved versioned instruction addendum, and CEO reporting rules.
- Create deterministic plans with `POST /plans`.
- Check free-first execution settings with `GET /runtime`.
- Generate ready-to-paste agent prompts with `POST /work-packets`; this makes no model/API call.
- Execute dependency-ready specialist steps through a durable worker queue when an owner-configured model endpoint is explicitly enabled.
- Run a persistent worker process with `python -m ai_os.worker_service`; see [docs/RUNNING_AGENTS.md](docs/RUNNING_AGENTS.md).
- Control the persistent worker through owner-authenticated `GET /worker/status` and `POST /worker/start`, `/worker/pause`, `/worker/resume`, and `/worker/stop`; active job leases renew during long-running handlers.
- Persist task, company-run, report, queue, knowledge, evaluation, and owner-reviewed training-example records in SQLite.
- Curate owner-reviewed model training examples in the dashboard and export accepted-only, versioned private JSONL datasets with SHA-256 manifests; this does not train a model.
- Inspect per-agent evaluation history and cautious sample-gated quality trends.
- Draft evidence-linked CEO improvement proposals; owner approval is required for testing, followed by a separate explicit owner-token activation action.
- Run static instruction-contract checks and optional local-only baseline-vs-candidate behavior regression tests for owner-approved proposals, then explicitly activate the exact passing addendum through the owner dashboard; activation is versioned, audited, and rollback-capable. No remote model endpoint or API key is allowed for behavior testing.

For the controlled Google Cloud Shell smoke-test procedure, see [docs/CLOUD_SHELL_SETUP.md](docs/CLOUD_SHELL_SETUP.md). It keeps model execution and external actions disabled until explicitly reviewed.

See [docs/FREE_FIRST_EXECUTION.md](docs/FREE_FIRST_EXECUTION.md) for the no-API workflow, [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) for registry and planning, [docs/AGENCY_AGENTS_ADOPTION.md](docs/AGENCY_AGENTS_ADOPTION.md) for source adoption, [docs/INSTRUCTION_VERSIONING.md](docs/INSTRUCTION_VERSIONING.md) for controlled improvement and rollback, [docs/BEHAVIOR_TESTING.md](docs/BEHAVIOR_TESTING.md) for optional local regression tests, [docs/OWN_MODEL_STRATEGY.md](docs/OWN_MODEL_STRATEGY.md) for the company-owned model plan, [docs/ACTION_GATEWAY.md](docs/ACTION_GATEWAY.md) for the approval execution boundary, [docs/OWN_MODEL_STRATEGY.md](docs/OWN_MODEL_STRATEGY.md) for private training-data curation and the owned-model plan, and [docs/ROADMAP.md](docs/ROADMAP.md) for the implementation sequence.

Approval is a server-enforced workflow, not an execution sandbox. No external adapter currently consumes approvals to publish, message customers, spend, deploy, or change production. Keep production integrations disconnected until a separately reviewed execution adapter is implemented. See [docs/ACTION_GATEWAY.md](docs/ACTION_GATEWAY.md).


## Optional model-backed specialist and CEO execution

- OpenAI-compatible presets are available for Gemini and Groq, plus local Ollama. Model execution remains disabled by default.
- Strict free-only mode defaults to on. Only the exact cloud-provider presets or localhost Ollama may run, and the exact model ID must be in `AI_OS_FREE_MODEL_ALLOWLIST`.
- Gemini/Groq additionally require a private API key and `AI_OS_MODEL_FREE_TIER_CONFIRMED=true` after the owner verifies the account plan and model. That setting is an attestation; the app cannot inspect provider billing.
- Free-tier limits, privacy terms, and model access vary. Quota errors stop the job without automatic retries or provider fallback. See [docs/PROVIDER_SETUP.md](docs/PROVIDER_SETUP.md) and [docs/PROVIDER_GEMINI_SETUP.md](docs/PROVIDER_GEMINI_SETUP.md).
- `GET /models/status` checks readiness without contacting a provider. `POST /worker/run-once` executes one durable job; `python -m ai_os.worker_service` runs a separately managed polling process. The API and worker must share the same persistent SQLite path.
- Specialists submit authenticated internal reports to the CEO. The CEO may produce a structured review but no model output can approve or execute spending, publishing, customer contact, or deployment.
- An optional local CLI backend uses `shell=False` but inherits its own permissions; strict free-only mode blocks it. Review [docs/RUNNING_AGENTS.md](docs/RUNNING_AGENTS.md) before intentionally changing that guard.


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
