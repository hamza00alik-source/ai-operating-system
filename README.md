# AI Operating System

A modular, human-supervised foundation for running an AI-powered company, with the complete pinned Agency Agents specialist library (283 profiles across 18 divisions).

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
# Configure a strong owner token before opening the dashboard.
export AI_OS_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf 'Owner token: %s\n' "$AI_OS_API_TOKEN"
uvicorn ai_os.api:app --reload
```

Open http://127.0.0.1:8000/docs.

Open the responsive owner dashboard at http://127.0.0.1:8000/dashboard. Enter the configured `AI_OS_API_TOKEN`; the dashboard reads agent, run, job, approval, runtime, and audit data from the protected API. The dashboard shell itself is public, but its data APIs still require owner authentication.

## Current capabilities
- Create and list work tasks and approval requests.
- Discover all imported specialists with `GET /agents` (CEO plus 283 Agency Agents profiles).
- Read a specialist's complete source instructions with `GET /agents/{agent_id}/profile`.
- Discover the pinned scenario team runbooks with `GET /runbooks` and `GET /runbooks/{slug}`.\n- Generate role-specific work packets that include the complete specialist profile and CEO reporting rules.
- Create deterministic plans with `POST /plans`.
- Check free-first execution settings with `GET /runtime`.
- Generate ready-to-paste agent prompts with `POST /work-packets`; this makes no model/API call.
- Persist task and approval records in SQLite.

See [docs/FREE_FIRST_EXECUTION.md](docs/FREE_FIRST_EXECUTION.md) for the no-API workflow, [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) for registry and planning, [docs/AGENCY_AGENTS_ADOPTION.md](docs/AGENCY_AGENTS_ADOPTION.md) for source adoption, and [docs/ROADMAP.md](docs/ROADMAP.md) for the implementation sequence.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authentication, authorization, audit logging, and integration safeguards exist.


## Phase 3: optional model-backed CEO review

- Provider-neutral OpenAI-compatible chat-completions adapter; no provider SDK or vendor is selected.
- Model execution is disabled unless `AI_OS_MODEL_ENABLED=true`, `AI_OS_MODEL_BASE_URL`, and `AI_OS_MODEL_NAME` are configured.
- Remote endpoints must use HTTPS; localhost model servers may use HTTP. API keys are read only from environment variables.
- `GET /models/status` checks readiness without contacting a provider.
- `POST /ceo/review/{run_id}` sends completed specialist reports to the configured model and stores its structured CEO review. It performs no actions.
- Reports are treated as untrusted input. Recommendations cannot dispatch agents, create approvals, publish, spend, or contact customers.
- Free-tier quotas, privacy, retention, and terms vary. No provider is enabled by default.
