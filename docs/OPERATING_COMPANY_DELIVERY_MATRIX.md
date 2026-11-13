# OpenCompany operating-company delivery matrix

**Status:** execution baseline, not a completion claim. This document separates capabilities already present in the development branch from the work required before OpenCompany can operate independently. It applies to `feature/opencompany-product-rd-workflow` and does not authorize production changes.

## Non-negotiable operating boundaries

- Business scopes are `core`, `physical-agency`, `physical-brand`, and `digital-products`. Core is internal-only. Never merge customer, supplier, catalogue, credential, order, cost, or revenue data across commercial businesses.
- Default operating budget is USD 0. Unknown or non-zero provider cost fails closed. No paid fallback, paid API, subscription, marketplace fee, hosting upgrade, or metered generation without owner approval.
- Agents may research, plan, draft, generate local artifacts, analyse, and prepare internal records. Publishing, sending external messages, binding quotes/commitments, purchases, payments, withdrawals, account/credential changes, production changes, deployment, and deletion remain owner-gated.
- No cold outreach. Prioritize inbound demand, search, marketplace discovery, and approved organic content.
- A role profile is not a running agent. Report execution only when a persisted lease/attempt, provider result, deliverable, audit event, and review state substantiate it.
- Current runtime is designed for one API process and one persistent SQLite volume. Multi-host worker coordination is not implemented.
- Existing production routing and production data are outside this development task. Do not merge, deploy, provision secrets, alter environment variables, or change routing without explicit owner authorization.

## 1. Autonomous workforce

### Present in development code

- Canonical CEO, ten department-manager and specialist role contracts.
- Business-scoped work items and dependency validation.
- CEO planning, manager delegation proposals, owner approval, durable queue admission, worker leases, heartbeat, retry/dead-letter handling, and review-required deliverables.
- Persisted agent handoffs, owner review, audit chain, cost-gated model gateway, explicit worker start/stop, and opt-in Product & R&D background coordinator.
- Worker-originated, bounded approval-intent submission into the owner inbox. The worker derives agent, task, and business identity from its validated lease; the agent cannot decide or execute an approval.

### Required to complete

1. Extend the existing durable attempt records and newly added owner-authenticated execution-history endpoint to cover heartbeat events, provider-call correlation/latency, cancellation detail, structured failure classes, and workflow-level aggregation. The current endpoint exposes ordered attempt number/status/timestamps/bounded error code, queue metadata and checkpoint metadata only.
2. Added owner-authenticated `/workers/health` metrics for queue age, expired leases, dead-letter count, worker fleet state, failed cycles, free-provider availability and business-filtered counts. Metrics are observational; no worker start/stop or recovery action is triggered by the endpoint.
3. Workflow-level orchestration that tracks parent/child tasks, parallel branches, dependencies, manager synthesis, rework, cancellation, pause/resume, and final outcome without relying on an operator to manually stitch each stage.
4. Durable scheduled-job definitions and missed-run/restart recovery. Scheduling must be opt-in, bounded, auditable, and disabled by default until configured.
5. Shared context/artifact references with business-scoped retrieval, provenance, access checks, retention, and explicit minimal cross-business handoffs.
6. Worker supervision, alert delivery for the newly exposed queue-age/lease-expiry/dead-letter metrics, graceful shutdown, process restart recovery, and a single-host deployment guard. Multi-host support requires a different coordination store and is a separate design.
7. Per-department operating procedures, machine-readable input/output contracts, manager quality gates, and evidence-based performance scorecards.
8. A true end-to-end manager → specialists → manager synthesis → CEO → owner review acceptance run with a verified zero-cost provider and ACTIVE role profiles.

**Acceptance evidence:** attempt timeline; deterministic recovery after process restart; completed parallel and sequential workflow; no cross-business data leakage; no cost overrun; review-required final deliverable; operator-visible failure and recovery; repeatable acceptance tests.

## 2. Business integrations

### Present in development code

- Owner-authenticated API Anything connector is read-only, tier-one only.
- Commercial records support business-scoped opportunities, suppliers, products, quotes, and orders.
- External-action request registry and owner approval inbox exist. Approval currently records `authorized_not_executed`; it is not an executor.
- Integration credentials are encrypted by the existing credential service. A first WooCommerce adapter now supports separately encrypted credentials for `physical-agency`, `physical-brand`, and `digital-products`; it exposes bounded, owner-triggered GET-only product/order reads and a read-only connection test. It minimizes order fields to omit customer PII, rejects non-HTTPS/IP/local hosts and nonstandard ports, blocks redirects, caps response size and pagination, and audits connection/read events. No store has been connected or live-tested.

### Required to complete

All connectors must have a per-business connection identity, least-privilege scopes, encrypted credentials, health/status reporting, rate limits, idempotency, audit correlation, data minimization, disconnect/revoke, and a read-only acceptance mode before writes are considered.

| Integration | First safe milestone | Later owner-approved capability |
|---|---|---|
| WooCommerce / owned store | **Implemented in code, not live-verified:** save per-business encrypted credentials; owner-triggered read-only test; bounded product/order reads (including stock fields and minimized order summaries) | Import/reconcile records, then draft product sync; owner-approved publish/update; approved fulfilment status updates |
| Marketplaces | Research/list supported channels and import read-only listing/order data where API access exists | Owner-approved listing submission and permitted order/fulfilment actions |
| Social channels | Read account/page metadata and prepare content drafts | Owner-approved scheduled publishing and analytics sync |
| Email / customer support | Read-only inbox import, classification and response drafts | Owner-approved message send; never autonomous commitments |
| Payments | Read-only payment/settlement status and reconciliation references | No payment initiation or withdrawal unless a separately approved, provider-specific workflow is built |
| Supplier / logistics | Supplier directory, product/lead-time/quote records and shipment status | Owner-approved supplier communication, purchase order or shipment booking |

Do not promise a connector until the provider's supported API, account eligibility, regional availability, scopes, terms, pricing, and current authentication flow have been verified. A generic API connector is not a substitute for a secure provider-specific adapter.

**Acceptance evidence:** separate credentials and records for each business; mocked contract tests; provider sandbox/read-only acceptance; retry/idempotency; revoked-token behavior; audit trail; no write side effects during read-only tests. WooCommerce now has static adapter/route coverage added, but those tests are deliberately unexecuted until the owner's testing pause ends; no live connection, provider response, credential revocation, or real-store reconciliation is claimed.

## 3. Revenue operations

### Present in development code

- Business-scoped commercial opportunity, supplier, product, quote and order records.
- Product & R&D nine-stage workflow with draft listing packet, artifact provenance, structural QA, and owner checkpoints.
- Owner approval inbox and model-usage cost reporting.
- Added schema-version-8 append-only financial event ledger, owner-verified event recording, business/order scope validation, source-reference idempotency, audit events, and per-business/per-currency summary endpoints.
- Revenue classification is model-aware: physical agency recognizes commission only; physical brand and digital products recognize their own sales; cash receipts are shown separately and are not double-counted as revenue. The ledger records evidence supplied and verified by the owner; it does not connect to a payment provider or initiate transactions.
- No live storefront, marketplace publishing, payment verification, customer messaging or automated fulfilment is currently proven operational.

### Required to complete

1. **Demand intelligence:** collect dated, attributable evidence for buyer segment, search intent, competitor offers, substitutes, willingness-to-pay signals, platform rules and risks. Separate observed facts from estimates.
2. **Product decision:** use a documented scorecard for buyer value, differentiation, production cost, support burden, IP/licensing, platform fit and realistic margin. Stop weak ideas rather than manufacture certainty.
3. **Product operations:** versioned specifications, source/provenance, deterministic builds where possible, QA reports, preview, packaging, licence review, support documentation and reproducible release artifacts.
4. **Channel preparation:** platform-specific listing copy, images, keywords, compatibility, price rationale, fees, refund policy and fulfilment plan. Listing remains a draft until owner approval.
5. **Inbound sales:** channel attribution, enquiry triage, qualification, response drafts, quote approval, order confirmation, customer status and escalation. No cold outreach.
6. **Fulfilment:** digital download entitlement/version delivery or physical supplier/stock/dispatch coordination, with idempotent status transitions and failure handling.
7. **Finance:** extend the newly added owner-verified, append-only ledger to reconcile separate revenue, commission, supplier payable, fees, taxes, refunds, chargebacks, cost of goods, fulfilment cost and net contribution against provider statements; add provider webhook ingestion only after secure read-only adapters exist. Never infer revenue from an order record alone.
8. **Feedback loop:** returns/refunds, support tickets, reviews, conversion, margin and product defects feed owner-reviewed product and marketing improvements.

Business-model-specific rules:
- `physical-agency`: recognize only the contractually agreed agency fee/commission as company revenue; supplier product gross value is not agency revenue.
- `physical-brand`: track the owner's brand sales, inventory/production costs, fulfilment, returns and margin independently.
- `digital-products`: track platform fees, refunds, taxes, licences, versions, download entitlement and support independently.

**Acceptance evidence:** ledger tests for model-specific revenue classification, per-business/per-currency isolation, duplicate source-reference rejection and order scope; then one fully reconciled synthetic order per business model; refund and cancellation path; duplicate webhook protection; fulfilment retry; owner approval at all protected boundaries; no real customer data in tests.

## 4. Production readiness

### Present in development code

- Owner authentication/session and CSRF safeguards, encrypted provider credentials, audit verification, health/readiness endpoints, SQLite backup export, non-root container guidance, and explicit one-process/persistent-volume deployment constraints.
- Deployment guide describes staging checks and warns that the existing Vercel rewrite still points to the legacy Railway API.

### Required to complete

1. **Verification:** after the owner's test pause, run the complete independent suite and CI, resolve failures, add coverage for all new integrations and approval boundaries, and record exact commit/workflow evidence. The new readiness endpoint is an evidence snapshot, not a substitute for this gate.
2. **Security:** independent review of authentication, authorization, tenant/business isolation, secret encryption/rotation, session revocation, CSRF, SSRF, file/path handling, dependency vulnerabilities, logs, rate limits and API exposure.
3. **Data durability:** verify SQLite WAL/backup behavior on the intended persistent volume; encrypted off-host backups; restore rehearsal; key recovery; documented RPO/RTO.
4. **Operations:** structured redacted logs, metrics, uptime/queue alerts, provider health, audit-chain checks, disk/DB growth monitoring, incident response and rollback runbooks.
5. **Runtime:** graceful worker shutdown/restart, lease recovery, memory/resource bounds, process health, non-root permissions, HTTPS, secure cookies, and no ephemeral DB.
6. **Staging:** deploy an isolated candidate only after owner approval; verify the exact commit, auth, readiness, worker lifecycle, backup/restore, integration sandbox, and mobile browser behavior.
7. **Cutover:** separate owner approval, maintenance window, verified backup, rollback rehearsal, exact routing diff and post-cutover smoke tests. Preserve the current legacy routing until all gates pass.

**Acceptance evidence:** green tests/CI on exact candidate SHA; independent security findings resolved or explicitly accepted; successful staging acceptance; restore and rollback evidence; owner-signed cutover decision; post-deploy smoke tests.

## Delivery order and definition of complete

1. Finish workforce orchestration and attempt/recovery observability.
2. Build business-isolated connector framework; start with read-only WooCommerce and platform-neutral commerce records.
3. Complete revenue lifecycle and accounting before enabling any writes or sales claims.
4. Complete security, backup/restore, monitoring and staging readiness.
5. Run tests after 2026-12-01 (or earlier only if the owner changes the existing pause), then owner-approved staging and production decisions.

A track is **complete** only when its implementation, acceptance evidence, operational limits, documentation, and recovery path all exist. A code commit, draft PR, role catalogue, connector stub, approval record, or successful deployment by itself is not completion.

## Current blockers and owner gates

- Testing/CI is paused through 2026-12-01 by prior owner instruction.
- No provider credentials or integration accounts are authorized/provisioned for these new connectors.
- No live customer/order/payment data or sandbox credentials have been supplied.
- No production deployment, merge, secret provisioning, spending, or external account mutation is authorized by this document.
- Existing PR #139 remains a draft and must not be merged merely because this delivery matrix exists.
