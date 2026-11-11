# Standalone OpenCompany application

The new product implementation lives in `src/opencompany_app` and `src/opencompany_core`. It is the only implementation target for the rebuild. The legacy `src/ai_os` application is retained as reference material and must not be modified by this workstream.

## Local development

Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export OPENCOMPANY_OWNER_API_KEY="use-a-long-random-secret"
export OPENCOMPANY_SECRET_ENCRYPTION_KEY="use-a-separate-random-secret-of-at-least-32-characters"
export OPENCOMPANY_DATABASE_PATH="data/opencompany_core.sqlite3"
uvicorn opencompany_app.api:app --reload
```

Supply secrets only through a private environment-variable manager. Use a persistent private volume for the database. The encryption key must remain stable while encrypted provider credentials are stored; rotating it requires re-entering those credentials.

## Internal execution lifecycle

The intended supervised workflow is:

1. Owner provisions the CEO, department managers, and original specialist profiles as drafts.
2. Owner explicitly activates only the profiles intended to execute work.
3. The active CEO converts an owner objective into a bounded dependency-aware draft plan.
4. An active department manager proposes a specialist team for each task. The proposal is validated against the original department and role contracts.
5. The owner approves the delegation proposal. Only then are assigned child work items materialized as READY.
6. The owner admits READY tasks into the durable queue. Queue admission checks active profile identity, department, role/team mapping, approval state, and completed prerequisites.
7. Workers atomically claim queued tasks, execute bounded internal text work through the zero-cost model gateway, and save review-required deliverables.
8. The owner reviews each deliverable, approves it or requests a revision. Failed tasks may be returned to READY by an owner before a new queue admission.
9. Handoffs, outcomes, learning proposals, provider usage, and lifecycle changes are persisted with audit evidence.

The worker has no shell, browser, publishing, purchasing, payment, customer-messaging, or other external-action authority. A generated draft is not a published product or customer commitment.

## Important API routes

Public, read-only:
- `GET /health` — process liveness.
- `GET /ready` — owner configuration and SQLite readiness; provider readiness is intentionally not required.
- `GET /workforce/roles` and `GET /organization/departments` — original OpenCompany role and department contracts.
- `GET /providers/candidates` and `GET /providers/status` — candidate and configured model status without secrets.
- `POST /plans/preview` — validates a proposed dependency graph without enqueueing or executing it.
- `GET /policy/protected-actions` — actions requiring owner approval.

Owner-authenticated:
- `POST /auth/session`, `GET /auth/session`, `POST /auth/logout` — exchange the owner key for a revocable HttpOnly browser session.
- `GET /owner/backup` — consistent, integrity-checked SQLite snapshot download.
- `GET /agents`, `POST /agents/bootstrap`, `POST /agents/bootstrap-executive`, `POST /agents/bootstrap-specialists` — profile provisioning.
- `POST /agents/{id}/state` — owner-controlled profile activation, pause, or retirement.
- `GET /work-items`, `POST /work-items`, `POST /executive/plan` — task and CEO planning.
- `POST /work-items/{id}/manager-proposal` and `POST /work-items/{id}/delegation-proposals` — manager planning and delegation proposals.
- `POST /work-items/{id}/delegation-proposals/{proposal_id}/approve` — owner approval and child-task materialization.
- `POST /work-items/{id}/enqueue` — owner admission to the durable queue.
- `GET /workers/queue`, `GET /workers/status`, `POST /workers/start`, `POST /workers/stop`, `POST /workers/{agent_id}/run-once` — queue and worker controls.
- `GET /work-items/{id}/workflow` — prerequisites, dependents, queue status, delegation proposals, handoffs, deliverables, and recommended next action.
- `GET /work-items/{id}/deliverables`, `POST /work-items/{id}/review`, `POST /work-items/{id}/transition` — owner review and lifecycle control.
- `POST /work-items/{id}/handoffs`, `GET /work-items/{id}/handoffs`, and handoff accept/decline/deliver routes — internal agent collaboration.
- `POST /work-items/{id}/evaluations`, `POST /learning/proposals`, `POST /learning/ai-proposals`, and learning decision/note routes — evidence-based quality improvement.
- `GET /usage/model` — durable secret-free model usage ledger.
- `GET /audit/verify` — verify the local audit hash chain.
- Provider settings, read-only API Anything research, and isolated GitHub code-evolution routes are owner-authenticated.

## Business-unit boundaries

Internal work items are assigned to one immutable business unit: `core`, `physical-agency`, `physical-brand`, or `digital-products`. CEO plans select one unit; manager-created child tasks inherit the parent unit; dependencies across units are rejected; workflow and task lists can be filtered by unit; role-learning notes are retrieved only for the matching unit; and model-usage costs can be reported per unit. Existing persisted work items migrate to `core` by default and can be recreated under a different unit only as new work.

This is internal workflow isolation, not yet complete external-account isolation. Store credentials, customer/order records, supplier records, financial ledgers, and marketplace accounts still need separate business-scoped connectors and authorization before those integrations are enabled.

## Provider and cost controls

No model provider is enabled by default. The UnoRouter integration imports the live public pricing catalogue and intersects it with model IDs visible to the owner's key. Only online chat-capable text models with exact zero input/output/fixed prices, a `:free` model ID, and key visibility are eligible. All eligible free models may be rotated; paid and unknown models remain unavailable. Provider-reported non-zero, invalid, or non-finite cost is rejected. If no eligible free model is available, execution fails safely.

The owner must review provider terms, privacy, data handling, account billing settings, and quotas. Use synthetic, non-sensitive input for the first live test. The model-usage ledger is provider-reported accounting, not an independent invoice.

## Worker lifecycle and re-admission

The API and in-process worker fleet share one SQLite database connection and transaction boundary. This deployment design assumes one persistent API container and one mounted SQLite volume; do not point a second host or standalone worker process at a separate copy of the database.

Queue leases are atomic and token-checked. Expired leases are recovered within a bounded retry ceiling; exhausted work is dead-lettered. An owner may return a FAILED item to READY, or request revision of a review item. The terminal queue row may then be reused for re-admission, with attempt and stale lease/error state reset. Existing queued or leased work cannot be overwritten.

The fleet may be started explicitly from the owner console. Optional autostart remains gated by the configured owner-approved provider verification in the current process; saved credentials alone do not authorize inference at process boot.

## Integrations and limits

- UnoRouter: optional live free-only inference adapter.
- API Anything: read-only, bounded research operations only.
- GitHub code evolution: isolated feature branch and draft pull request only; no auto-merge or deployment.
- WooCommerce, social publishing, customer email/support, marketplace publishing, fulfillment, and payment-status verification are not yet connected as operational workflows.
- LongCat-Video is a researched capability, not an active generation service; it requires suitable GPU hardware, dependencies, and model weights.

No autonomous spending, purchases, publishing, customer communications, payment actions, withdrawals, or customer commitments are permitted. Explicit owner approval remains mandatory for protected external actions.

## Operational readiness

The owner console is mobile-friendly and exposes workforce, planning, delegation, queue, review, provider, usage, learning, and workflow-detail controls. A manual consistent backup export is implemented; automated off-host backup retention and restore rehearsal are not yet complete.

Before production routing is changed, verify the persistent volume, owner session recovery, saved provider configuration, authenticated live free-model test, worker execution while the owner is offline, backup restore, audit-chain integrity, and rollback. A successful deployment or passing unit tests alone is not proof of end-to-end production readiness.

CI/testing is deferred until 1 December 2026 under the owner's current instruction. Newly added regression tests must be treated as unrun until that date or until the owner changes the instruction.
