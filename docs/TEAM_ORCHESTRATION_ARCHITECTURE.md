# OpenCompany Team Orchestration Architecture

**Reference:** Teamily.ai, used as an inspiration benchmark only. OpenCompany does not copy its branding, proprietary implementation, or unverified capability claims.

## Design objective

Make OpenCompany AIOS one coordinated operating system: a CEO-led orchestration layer, specialist teams, shared but access-controlled company knowledge, durable workflows, free-only model routing, useful deliverables, and explicit owner approval gates.

## Non-negotiable company boundaries

Every task belongs to exactly one business environment:

- `physical-agency`: third-party physical-product supplier/manufacturer agency. AIOS supports international buyer research, marketing, enquiries, sales coordination and reporting; the owner manages the Pakistan-side physical supply chain.
- `physical-brand`: the owner's separate physical-products brand, with its own customers, products, supply chain, sales, finances and operations.
- `digital-products`: the separate downloadable digital-products business.
- `core`: internal OpenCompany platform work only.

A workflow must never fulfil a physical order with a digital deliverable, promise physical shipment from the digital-products business, or merge the agency and owned-brand customers or finances. If a task is mis-scoped or ambiguous, it must be flagged for owner correction rather than silently reassigned.

## Teamily-inspired patterns and AIOS implementation

| Pattern | AIOS implementation | Current truth |
|---|---|---|
| CEO-led team | Lead specialist, independent collaborator, CEO integration/QA | Existing three-stage runtime; now receives a shared team contract |
| Specialized workforce | Agency Agents catalogue mapped to company departments | Catalogue is not a set of always-on agents |
| Shared memory | Business-scoped brain retrieval and experience capture | Existing subsystem; approved memories only are retrieved |
| Shared workspace | Persisted task, run, step, event, workflow and department-inbox records | Existing persistence; richer artifact aggregation remains open |
| Model routing | UnoRouter-first, free-confirmed provider failover | Existing routing; no paid fallback |
| Human control | Owner approval for external/consequential actions | Existing policy; external write integrations remain unconnected/disabled |
| Proactive execution | Worker queues and scheduled brain evaluation | Bounded in-service workers; not a claim of independent cloud agents or guaranteed operation while offline |
| Team planning | Task intent and department-aware specialist selection | Partial; autonomous CEO task decomposition and dynamic team sizing remain future work |

## Runtime contract added in this change

The same explicit business-scope and team-operating contract is injected into the lead specialist, collaborator and CEO review prompts. Unknown business IDs fail closed. The team contract requires role distinction, critical independent review, CEO integration, source/evidence discipline, and prohibits cross-business context disclosure.

This is a prompt-level execution guardrail in addition to the existing database-level business-scoped task and memory retrieval. It is not a substitute for authorization, row-level isolation, or external-action approval enforcement.

## Target execution lifecycle

1. Owner or authorized internal workflow creates a task in one business environment.
2. CEO/planner classifies objective, deliverable type, department, dependencies, risk and approval requirements.
3. Orchestrator selects a lead specialist and one or more reviewers from the correct department pool.
4. Agents receive only the current task's scoped instructions, approved memories and captured research evidence.
5. Work proceeds through a durable queue; each stage writes its output, model/provider metadata and execution events.
6. CEO integrates outputs, checks business scope, evidence, completeness and acceptance criteria.
7. Deliverables are stored against the task/workflow; downstream departments unlock only after successful handoff.
8. Internal reversible work may continue within policy. Publishing, spending, customer communications, purchases, payments, account changes and commitments remain blocked pending explicit owner approval.
9. Outcomes and failures are recorded in the correct business brain. Proposed lessons require owner review before retrieval.

## Required next engineering increments

- Add a structured task/team plan with typed deliverables and acceptance criteria.
- Replace fixed collaborator selection with intent-aware reviewer selection and bounded team size.
- Aggregate workflow artifacts and support safe cancellation, resumability, retry budgets and dependency-aware parallel branches.
- Add worker leases/heartbeats and shared durable queue semantics before multi-replica operation.
- Complete business-level isolation for research sources, credentials, customers, finance, integrations and dashboard access.
- Add connector permission scopes and a central approval service before any external write integration.
- Build evaluation fixtures for wrong-business fulfilment, cross-business retrieval, prompt injection, evidence provenance, invalid model JSON, paid-model exclusion and partial-run recovery.
- Redesign the mobile owner dashboard around actual team/workflow state, artifacts, blockers, approvals and provider health. Dashboard counts must be sourced from persisted records, never simulated.

## Verification boundary

A code commit is not proof of a passing test, successful Railway deployment, working provider inference, connected marketplace, or autonomous operation. Record each separately and only mark a capability verified after observing its actual test or runtime evidence.


## Deterministic business-line intake controls

The runtime now applies a deterministic, conservative fulfillment-intent check at task intake and internal delegation. Physical-agency and physical-brand tasks are rejected when their wording explicitly asks to substitute a digital deliverable for an order. Digital-products tasks are rejected when they explicitly promise physical goods, inventory, manufacturing or shipping. Unknown business IDs fail closed.

The dedicated digital-product-launch workflow is restricted to the digital-products environment. Task execution and workflow-detail reads also verify the selected business ID, returning a not-found response rather than exposing another business line's records.

These checks are a safety layer, not a complete semantic classifier or database row-level security system. They deliberately focus on explicit fulfillment language to avoid blocking ordinary cross-channel marketing or research references. They require adversarial testing and further expansion to all customer, finance, credential, integration and artifact endpoints before claiming full business isolation. Unit tests have been added but remain unexecuted while CI is deferred until December 1.

## OpenCompany is an expandable multi-business company

The three current business lines are initial operating units, not a limit on the company's ambition. OpenCompany's company-level objective is to discover, validate, launch and grow any legitimate business opportunity with credible profit potential. New opportunities may include physical products, digital products, software/SaaS, services, content/media, licensing, partnerships, commerce or other viable models.

A persistent business-unit registry now supports owner-controlled creation of additional ventures. Each new unit receives its own stable business ID, business name, business type and operating description. The dashboard loads business selectors from the registry rather than relying on a fixed list. The CEO/agent runtime can build a dedicated scope contract from the registered unit's description, while customer records, financial records, research, credentials and approved memory remain keyed to that business ID.

The three existing physical-agency, own-physical-brand and digital-products units remain distinct with their original restrictions. New venture registration does not itself authorize spending, publishing, purchases, external account changes or customer commitments; those actions remain approval-gated. New ventures are not automatically assumed to be profitable or launched merely because they are registered: research, validation, risk review and owner approval remain required.

The registry is a first expansion step, not a complete venture lifecycle manager. Deactivation/archive controls, venture P&L rollups, opportunity scoring, capital allocation, cross-business portfolio reporting and automated venture launch playbooks remain future work.

## Venture Discovery & Growth — company-wide opportunity portfolio

OpenCompany's profit objective is broader than the three initial business units. A company-level Venture Discovery & Growth department evaluates opportunities across industries and legitimate business models. Its company-wide portfolio is kept separate from the books and private operating context of each venture.

The first implementation adds a persistent opportunity register with an owner-entered thesis, customer segment, problem, revenue model and market scope. An owner can queue a structured research task through the existing AI worker and the company department registry routes that task to the Venture Discovery & Growth department, which maps to the available research, finance, product, marketing, sales, specialist and academic catalogue pools. This is catalogue-routed collaboration, not a claim that every mapped role is a separately running agent or that all research sources are automatically live.

The research brief requires dated, source-backed facts; clear separation of facts, estimates, hypotheses and unknowns; customer demand and willingness-to-pay analysis; competitors and substitutes; pricing; startup and recurring costs; unit economics and break-even assumptions; distribution and acquisition costs; operational feasibility; legal/IP risks; and a low-cost validation experiment. It forbids invented market figures, sources, demand and profit claims. Research uses the existing free-confirmed model routing and does not authorize paid inference or external actions.

A six-dimension 0–5 scorecard (demand, competition, economics, distribution, execution, risk) produces a clearly labelled provisional score only when all six ratings are supplied. The score is not a probability of success and is not automatically generated from unverified claims. Launch planning approval is blocked until all six ratings and at least three HTTPS evidence sources are recorded. Only an owner-authorized launch action registers a new, separate business unit; registration itself spends no money, publishes no listing and contacts no customer.

This is an initial venture funnel, not yet a full investment committee or autonomous portfolio manager. Live market data retrieval, source quality verification, financial model generation, validation experiment tracking, portfolio P&L, performance-based scaling/pivot/closure recommendations and scheduled recurring opportunity scans remain future work.
