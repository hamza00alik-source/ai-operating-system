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

## Company structure

The canonical ownership, business-unit, shared-service, and data-isolation rules are documented in [COMPANY_STRUCTURE.md](COMPANY_STRUCTURE.md). The three commercial businesses are `physical-agency`, `physical-brand`, and `digital-products`; `core` is reserved for genuinely company-wide platform/governance work and is not a fourth commercial business.

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
- `GET /work-items?business_id=...`, `POST /work-items`, `POST /executive/plan` — business-scoped task and CEO planning.
- `POST /work-items/{id}/manager-proposal` and `POST /work-items/{id}/delegation-proposals` — manager planning and delegation proposals.
- `POST /work-items/{id}/delegation-proposals/{proposal_id}/approve` — owner approval and child-task materialization.
- `POST /work-items/{id}/enqueue` — owner admission to the durable queue.
- `GET /workers/queue`, `GET /workers/status`, `POST /workers/start`, `POST /workers/stop`, `POST /workers/{agent_id}/run-once` — queue and worker controls.
- `GET /work-items/{id}/workflow` — prerequisites, dependents, queue status, delegation proposals, handoffs, deliverables, and recommended next action.
- `GET /work-items/{id}/deliverables`, `POST /work-items/{id}/review`, `POST /work-items/{id}/transition` — owner review and lifecycle control.
- `POST /work-items/{id}/handoffs`, `GET /work-items/{id}/handoffs`, and handoff accept/decline/deliver routes — internal agent collaboration.
- `POST /work-items/{id}/evaluations`, `POST /learning/proposals`, `POST /learning/ai-proposals`, and learning decision/note routes — evidence-based quality improvement.
- `GET /usage/model?business_id=...` — durable secret-free model usage ledger, filterable by business unit.
- `GET /workers/queue?business_id=...` and `GET /learning/proposals?business_id=...` — business-scoped operational queue and learning views.
- CEO plans, manager-generated child tasks, specialist research/model requests, evaluations, approved learning notes, and model usage retain the originating work item's business-unit identity.
- `GET /audit/verify` — verify the local audit hash chain.
- Provider settings, read-only API Anything research, and isolated GitHub code-evolution routes are owner-authenticated.

## Business-unit boundaries

Internal work items are assigned to one immutable business unit: `core`, `physical-agency`, `physical-brand`, or `digital-products`. CEO plans select one unit; manager-created child tasks inherit the parent unit; dependencies across units are rejected; workflow and task lists can be filtered by unit; role-learning notes are retrieved only for the matching unit; and model-usage costs can be reported per unit. Dependency artifacts are re-checked against the requesting task's business unit and completion state at runtime before their content is loaded into another agent's context; returned dependency context carries the originating business ID. Existing persisted work items migrate to `core` by default and can be recreated under a different unit only as new work.

This is internal workflow isolation, not yet complete external-account isolation. Store credentials, customer/order records, supplier records, financial ledgers, and marketplace accounts still need separate business-scoped connectors and authorization before those integrations are enabled.

## Provider and cost controls

No model provider is enabled by default. The UnoRouter integration imports the live public pricing catalogue and intersects it with model IDs visible to the owner's key. Only online chat-capable text models with exact zero input/output/fixed prices, a `:free` model ID, and key visibility are eligible. All eligible free models may be rotated; paid and unknown models remain unavailable. Provider-reported non-zero, invalid, or non-finite cost is rejected. If no eligible free model is available, execution fails safely.

The owner must review provider terms, privacy, data handling, account billing settings, and quotas. Use synthetic, non-sensitive input for the first live test. The model-usage ledger is provider-reported accounting, not an independent invoice.

## Worker lifecycle and re-admission

The API and in-process worker fleet share one SQLite database connection and transaction boundary. This deployment design assumes one persistent API container and one mounted SQLite volume; do not point a second host or standalone worker process at a separate copy of the database.

Queue leases are atomic and token-checked. Expired leases are recovered within a bounded retry ceiling; exhausted work is dead-lettered. An owner may return a FAILED item to READY, or request revision of a review item. The terminal queue row may then be reused for re-admission, with attempt and stale lease/error state reset. Existing queued or leased work cannot be overwritten. The owner console exposes retry for FAILED work and cancellation for unqueued work. State-only cancellation of QUEUED or IN_PROGRESS work is rejected because it would leave an orphaned queue row or active provider call; queue-aware cooperative cancellation remains a release task.

The fleet may be started explicitly from the owner console after a successful owner-triggered zero-cost provider test. Alternatively, the owner may explicitly set `OPENCOMPANY_WORKER_AUTOSTART=true`; on restart, the API starts the in-process fleet only when the owner key is configured and the gateway reports a zero-cost eligible provider. Every model request is still checked by the strict free-only gateway and fails closed if the live free catalogue or key access is unavailable. Autostart never grants external-action authority.

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

### Commercial opportunity and catalogue isolation

The owner API now provides private, owner-authenticated commercial records:

- `POST/GET /commercial/opportunities`: each opportunity must select exactly one of `physical-agency`, `physical-brand`, or `digital-products`. Core is internal and cannot own a customer opportunity. Creation requires an explicit single-business scope confirmation.
- `POST/GET /commercial/products`: each catalogue entry is stored under one commercial business unit and begins as a private `draft`. No publish/listing action is provided by these endpoints.
- Each create operation and its audit event are committed in the same SQLite transaction. Lists can be filtered by business unit.
- An owner can explicitly approve a draft catalogue entry for internal matching; the approval is audited and does not publish or list the product externally. An opportunity's matching-catalogue endpoint filters strictly to that opportunity's own business unit and returns active entries only.
- These are initial records, not a complete CRM, quoting, order, inventory, payment, supplier, or marketplace system. Customer contact, publishing, pricing commitments, orders, and cross-business referrals remain unavailable until separately designed and owner-approved.
- No cross-selling or substitution feature exists. A second independently requested category must be represented as a separate opportunity with its own business unit and scope confirmation.

### Proposals, quotations, and orders

- A quote belongs to one opportunity and inherits its immutable business unit. Every quote line must reference an active catalogue item from that same unit; mixed-business quotes are rejected in the persistence layer.
- Quote amounts are stored as integer minor currency units with an explicit currency exponent (0–3 decimal places) to avoid assuming every currency has two decimals. Quotes begin as drafts. Owner approval moves a quote to `approved_for_delivery`, which means it is ready for manual owner delivery only; the application does not send it.
- Customer acceptance is recorded only after an owner confirms acceptance and supplies an evidence reference. A quote can be accepted only after it was approved for delivery.
- An order record can be created only from an accepted quote, requires explicit owner confirmation, and is unique per quote. This records an order awaiting owner fulfilment; it does not take payment, contact the customer, commit a supplier, or start fulfilment.
- Quote, decision, and order writes are transactional with their tamper-evident audit events. Orders and quotes retain their opportunity's business unit.

- Creating the first quote advances its opportunity to the proposal stage; recording an accepted-quote order advances the opportunity to won. Both stage changes are part of the same transaction as the quote/order audit record.

- Lost and on-hold opportunities cannot receive new quotes. An accepted quote cannot be voided after its order record exists, and duplicate order creation is rejected.

- Order status can be changed only through owner-confirmed, audited transitions: awaiting owner fulfilment → in progress → fulfilled, with cancellation allowed before completion. These status updates are records only and never trigger external fulfilment.


### Supplier relationship records (schema 7)

- Private supplier records are available only to the physical-products agency and the owner's own physical-product brand. Digital products and core cannot own supplier records.
- Agency suppliers represent third-party manufacturers/suppliers the agency may represent; own-brand suppliers belong only to the owner's separate supply chain. The relationship type is derived from the business unit and enforced by a database constraint.
- Supplier records begin as drafts. Owner-confirmed status changes can mark a record verified or blocked; every write and status change is audit-linked in the same database transaction.
- Listing can be filtered to one physical business. No supplier credentials, purchase orders, inventory claims, supplier messages, price commitments, or procurement actions are created by this registry.
- A verified supplier is not proof of stock, quality certification, export eligibility, or current pricing. Those require separate evidence and review.
