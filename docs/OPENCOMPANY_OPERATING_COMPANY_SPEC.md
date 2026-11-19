# OpenCompany operating-company specification

Status: implementation requirements for the OpenCompany rebuild. This document is a design and acceptance specification, not evidence that the listed capabilities are already operational.

## 1. Product objective

OpenCompany is one owner-controlled operating company, not a collection of disconnected chat agents. It must coordinate specialized AI workers, departments, persistent business context, business-unit workflows, finance controls, integrations, and measurable commercial outcomes.

The owner remains the final authority for external commitments, publishing, customer communication, payments, purchases, budget increases, integration permissions, production changes, and other consequential actions.

This specification applies only to OpenCompany in this repository. It does not describe or merge the separate Autonomous AI Economy project.

## 2. Lessons extracted from the supplied video

The video depicts an AI-operated town/company with:
- A central leadership/Town Hall concept and individually inspectable agents.
- Agent profiles with Overview, Live, Messages, Memory, and Prompt surfaces.
- Specialist workspaces, including a Merch Studio with Pitch, Stitch, and Vector.
- Product concepts connected to an online shirts storefront.
- A business dashboard showing views, fans, revenue, MRR, posts, spending, and a first-revenue mission.
- Shared infrastructure and resource/usage indicators, including rolling five-hour and seven-day limits.
- A dedicated Bank agent named Penny, a stated $200 card limit, and a separate $100 advertising budget.

The recording shows $0 revenue and $0 MRR at the displayed dashboard snapshot. The creator's $1,000 figure is a target, not verified earnings. The token figures and budgets are creator-reported interface values, not independently audited measurements.

These observations are reference patterns, not proof of the underlying implementation or business results.

## 3. OpenCompany organizational model

### 3.1 Company leadership
- Owner: sets objectives, approves consequential actions, controls budgets and credentials, and reviews company performance.
- CEO orchestrator: converts owner objectives into bounded plans, coordinates department managers, tracks dependencies, evaluates deliverables, and reports blockers.
- Department managers: break approved objectives into specialist work, synthesize results, and escalate risks.
- Specialists: perform scoped work using their canonical role, capability set, business-unit context, approved knowledge, and assigned tools.

The existing 511 role definitions are a catalogue of role definitions, not 511 concurrently running agent processes. Runtime agent instances must be provisioned and activated explicitly.

### 3.2 Departments
Use the existing OpenCompany-owned department catalogue:
1. Research & Intelligence
2. Product & R&D
3. Engineering & Technology
4. Design & Creative Production
5. Marketing & Growth
6. Sales & Marketplace Operations
7. Customer Operations
8. Finance & Accounting
9. Legal & Compliance
10. Quality & Workforce Operations

### 3.3 Business-unit isolation
Keep the three existing business units distinct:
- Physical-products agency.
- Own physical-products brand.
- Digital products.

Every task, memory, asset, credential, integration, financial record, customer/order record, and deliverable must have an explicit business-unit scope where applicable. Cross-business access must be denied by default and explicitly justified when introduced.

## 4. Required agent workspace

Every provisioned agent should have an owner-inspectable workspace with:
- Overview: stable identity, role, department, team, capabilities, state, business scope, revision, and assigned manager.
- Live: current task, execution state, heartbeat, last activity, provider/model, usage, and failure state.
- Messages: durable delegation, status, handoff, and synthesis history.
- Memory: approved shared and business-specific memories, sources, provenance, retention, and owner review state.
- Prompt: versioned OpenCompany-authored role instructions, tool permissions, and policy constraints.
- Deliverables: draft outputs, evidence, QA results, revision history, and owner decisions.

A profile marked active is not proof of a running process. UI and API must distinguish role catalogue entries, provisioned profiles, active profiles, executing workers, and completed task outcomes.

## 5. End-to-end operating loop

The target operating loop is:

1. Owner creates or approves a business objective.
2. CEO drafts a bounded plan with success criteria, business-unit scope, budget ceiling, risks, and dependencies.
3. Department managers prepare specialist-team proposals.
4. Owner approves the plan/delegation before child work is materialized or admitted to execution.
5. Scheduler checks dependencies, role match, active state, business scope, permissions, and available resource budget.
6. Worker claims work using a durable lease and executes the assigned specialist task.
7. Specialist returns a structured draft with source evidence, artifacts, assumptions, costs, and unresolved questions.
8. Manager synthesizes team outputs and checks completeness.
9. Quality reviewer evaluates the deliverable against a role-specific rubric.
10. CEO evaluates the workflow and proposes next steps.
11. Owner reviews the deliverable and separately approves any external action.
12. System records the result, audit event, usage, costs, revenue impact, and reusable-memory proposal.

Failures must be visible, recoverable, and idempotent. A restart must not duplicate payments, publishing, customer messages, deliverables, or queue admissions.

## 6. Resource and model management

Implement a company-wide resource controller with:
- Per-task, per-agent, per-department, per-business, and company-wide budgets.
- Token and provider-reported cost accounting, with explicit unknown values when providers do not report usage.
- Rolling provider quota windows and rate-limit handling.
- Provider/model eligibility checks, current pricing/terms evidence, region and privacy checks, and owner confirmation.
- Task complexity-based model routing, only among owner-authorized eligible providers.
- Concurrency limits, timeouts, cancellation, lease renewal, retry/backoff, and circuit breakers.
- Budget reservations before work and reconciliation after work.
- Pause/resume of affected tasks when quotas are exhausted; unrelated eligible work may continue.
- No silent paid fallback. The existing zero-cost-only policy remains in force until the owner explicitly changes it.

Token counts are not currency and must never be represented as revenue, cash, or company-owned crypto assets.

## 7. Finance and bank operations

The Finance department must provide:
- Append-only income and expense ledger.
- Business-unit and currency separation.
- Owner-visible cash position only when connected, verified source data supports it.
- Revenue, recurring revenue, refunds, fees, cost of goods, operating costs, gross margin, and net profit metrics with explicit definitions.
- Invoice and payout evidence, transaction matching, reconciliation, and discrepancy queues.
- Budget proposals, spending caps, approval records, and immutable audit history.
- Read-only payment-status verification where a verified integration supports it.

A finance agent may research, calculate, categorize, forecast, and prepare payment instructions. It must not initiate payments, move funds, change bank details, or spend from a card without a separate explicit owner authorization and a reviewed action-specific executor.

The video’s $200 card and $100 ad cap are examples from the creator's environment, not OpenCompany budgets.

## 8. Product, marketing, sales, and fulfillment

The company must support a complete business workflow:
- Opportunity research and evidence capture.
- Customer/problem and competitor analysis.
- Product specification, creation, QA, licensing/IP checks, and packaging.
- Product catalogue, supplier, pricing, inventory, and unit-economics records.
- Storefront/listing drafts with platform-specific requirements.
- Marketing plans, content assets, campaign budgets, and performance attribution.
- Lead and enquiry capture, response drafts, owner-approved customer communication.
- Orders, payment-status verification, fulfillment coordination, returns, and support.
- Revenue and profit attribution back to the correct business unit and campaign.

External storefront, CRM, email, analytics, and marketplace connections must be verified and permission-scoped. Draft creation is not publication; a payment-status signal is not proof of settled funds; a listing is not a sale.

## 9. Owner control center

The owner console should provide a real, mobile-friendly operational view:
- Company overview: verified revenue, expenses, profit, orders, customers, workload, and current blockers.
- Organization: departments, managers, provisioned agents, and agent state.
- Agent workspace: Overview, Live, Messages, Memory, Prompt, Deliverables.
- Work management: objectives, plans, dependencies, queues, leases, task history, retries, cancellation, and review.
- Resource center: model/provider status, usage, quotas, budget reservations, and spend warnings.
- Finance: ledger, reconciliation, budget proposals, and approvals.
- Business units: isolated context, assets, credentials, integrations, products, customers, and operations.
- Approval inbox: action, exact scope, evidence, consequences, budget, and approve/reject decision.
- Audit and health: authentication, worker heartbeat, failures, backup age, restore evidence, and integration status.

Every metric must disclose its source and freshness. Missing or unverified values must be shown as unknown, not zero. A visually impressive town map may be added later as an optional visualization; it is not a substitute for functioning APIs or controls.

## 10. Persistence, security, and reliability

Required production properties:
- Persistent database and private asset storage with documented backup and restore.
- Durable queue leases, heartbeat renewal, stale-worker fencing, bounded retries, cancellation, and crash-safe result persistence.
- Multi-process/multi-worker coordination before horizontal scaling.
- Strong owner authentication, CSRF protection, session rotation/expiry, least privilege, rate limits, and secret redaction.
- Business-unit access isolation and encrypted credentials.
- Append-only audit records for approvals, agent state changes, financial decisions, integrations, and external actions.
- Dependency and supply-chain review, threat model, security review, monitoring, alerting, log retention, and disaster recovery.
- Mobile acceptance and operational runbooks.

## 11. Definition of fully functional

OpenCompany is not fully functional merely because the API starts, the dashboard loads, agents appear in a catalogue, or tests pass.

The company-level acceptance gate requires evidence of all of the following in an isolated staging environment before production:
1. Owner objective to CEO plan to manager proposal to specialist execution to manager synthesis to quality review to owner acceptance works end to end.
2. Multiple independent tasks can run concurrently without cross-business data leakage, duplicate work, lost leases, or corrupt deliverables.
3. Shared and business-specific memory retrieval is source-attributed, permission-checked, reviewable, and persistent across restart.
4. Resource limits, usage records, provider failures, pauses, retries, and recovery behave as designed without paid fallback.
5. Finance ledger, reconciliations, budget controls, and revenue/profit calculations reconcile against test evidence.
6. At least one real, owner-authorized business workflow completes from product/opportunity through an external customer transaction and fulfillment, with every external action explicitly approved and auditable.
7. Integrations are connected with least-privilege permissions and tested against real sandbox/test accounts before live access.
8. Backup restoration, process restart, worker recovery, monitoring, security review, and Android/mobile acceptance pass.
9. Production release is separately approved by the owner.

## 12. Implementation order

1. Finish the company control center and agent/work/finance/resource observability using existing APIs.
2. Complete durable orchestration: manager synthesis, parallel scheduling, task schemas, cancellation, retries, lease renewal, and crash-safe persistence.
3. Complete source-attributed shared memory and quality/evaluation.
4. Complete business-unit product, supplier, storefront, customer, order, and fulfillment workflows.
5. Complete finance reconciliation and owner-authorized external action executors.
6. Complete integrations, worker hosting, persistence, backups, security, and mobile acceptance.
7. Run the full staging acceptance programme and only then request production-release approval.

## 13. Current known limitations from the inspected repository

The current branch already contains useful foundations, but its roadmap still identifies major gaps: full CEO execution loop, parallel scheduling, workflow artifact aggregation, durable execution recovery, lease renewal, multi-worker support, source-attributed knowledge, shared memory, evaluations, live provider validation, verified external integrations, product/supplier/order/fulfillment workflows, payment-status verification, and production hosting/security/backup acceptance.

The owner HTML route in `src/opencompany_app/api.py` now includes owner sign-in, company refresh, workforce provisioning/state changes, business-scoped draft work creation, department visibility, worker/queue status, model usage, finance-ledger visibility, task workflow details, prerequisite/dependent and deliverable inspection, specialist-team proposal creation, owner approve/reject decisions, deliverable review, CEO readiness advancement, queue admission, explicit worker start/stop/single-task controls, owner-written business memory with source attribution, and read-only views of business-scoped integration and credential references. The dashboard and core suites passed GitHub Actions on commit `af4894d41d6fb78615266feb72f4aaed1ab22465` (210 full-suite tests and 18 core tests). Live runtime acceptance is still outstanding. The Vercel preview is READY but unauthenticated routes redirect to Vercel SSO; additionally, the checked-in `vercel.json` rewrites all routes to the existing Railway production AIOS host and `pyproject.toml` still declares `src.ai_os.api:app` as the Vercel entrypoint. The preview is therefore not an isolated OpenCompany staging runtime and must not be used to validate OpenCompany routes. No production configuration was changed. This console is still incomplete: full finance reconciliation, integration registration/permission review, shared-memory search/history/review controls, comprehensive failure recovery, and richer agent workspaces remain outstanding. The separate worker is single-instance and opt-in. The worker does not create customer-facing or financial side effects without separate owner approval. These limits must remain explicit until the corresponding functionality is implemented and verified.
