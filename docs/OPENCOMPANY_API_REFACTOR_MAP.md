# OpenCompany API Refactor Map

Status: active refactor record. Request-schema and runtime/auth dependency extraction, duplicate workflow-route consolidation, catalogue/system/provider/GitHub/API Anything/agent/worker/work-item/handoff/orchestration/lifecycle/learning/commercial/venture-portfolio and owner-session and operational-diagnostics and planning/queue router extractions are implemented on the development branch. Route behavior and runtime correctness remain unverified until the deferred test window.

## Scope and evidence

Inspected `src/opencompany_app/api.py` on branch `feature/opencompany-aios-unification`; latest API blob SHA after operational-diagnostics extraction: `532999a0a3c98d73005dc190d4904762d3f7db34`.

- Before duplicate-route consolidation, the module was approximately 3,360 lines and had 96 route decorators; the duplicate was removed, leaving 95 route decorators.
- `src/opencompany_app/api.py` no longer declares request models. The 36 original Pydantic request models now live in `src/opencompany_app/api_schemas.py`; static comparison against the pre-extraction API source confirms each class body is byte-for-byte identical.
- The API now has four direct HTTP route decorators in `api.py`, two work-item creation/listing routes in `routers/work_items.py`, five worker queue/fleet routes in `routers/workers.py`, five agent/workforce routes in `routers/agents.py`, six read-only API Anything routes in `routers/integrations.py`, seven GitHub integration/code-evolution routes in `routers/github_evolution.py`, eight UnoRouter routes in `routers/providers.py`, two health/readiness routes in `routers/system.py`, four read-only catalogue routes in `routers/catalogue.py`, five handoff routes in `routers/handoffs.py`, five planning/delegation routes in `routers/orchestration.py`, four work-item lifecycle/review/deliverable routes in `routers/lifecycle.py`, nine outcome-evaluation/learning routes in `routers/learning.py`, twelve commercial opportunity/product/quote/order routes plus three supplier routes in `routers/commercial.py`, four company-wide venture portfolio routes in `routers/portfolio.py`, three owner browser-session routes in `routers/auth.py`, one owner backup route and two owner diagnostics routes in `routers/operations.py`, two planning/policy routes, one guarded queue-admission route and one delegation-preview route in `routers/planning.py` (95 total HTTP route registrations by static composition count). The routers are included at their original route-group positions.
- The app package now includes `api_schemas.py`, `api_dependencies.py`, and a `routers/` package with `catalogue.py`, `providers.py`, `system.py`, `github_evolution.py`, `integrations.py`, `agents.py`, `workers.py`, `work_items.py`, `handoffs.py`, `orchestration.py`, `lifecycle.py`, `learning.py`, `commercial.py`, `portfolio.py`, `auth.py`, `operations.py` and `planning.py`, in addition to the composition, dashboard and runtime modules.
- `api.py` now imports its cached runtime singleton, runtime/store dependencies, login throttling helpers, and owner-authentication dependency from `api_dependencies.py`. Application startup/shutdown hooks remain in `api.py` and use the same imported singleton. Request schemas are isolated in `api_schemas.py`.
- This is a static source inspection. No tests, imports, server startup, or runtime route-resolution checks were performed.

## Completed schema inventory

All 36 Pydantic request models have been moved to `api_schemas.py`. Their class bodies were statically compared against the pre-extraction API source and were byte-for-byte identical:

- Authentication/provider settings: `OwnerLoginInput`, `UnoRouterSettingsInput`, `UnoRouterDiscoveryInput`, `GitHubEvolutionSettingsInput`
- Venture portfolio: `VentureOpportunityInput`, `VentureOpportunityStatusInput`
- Planning/workforce: `PlanItemInput`, `PlanPreviewInput`, `WorkforceRoutePreviewInput`
- Agents/work: `AgentStateChangeInput`, `WorkItemCreateInput`, `WorkItemTransitionInput`, `WorkItemReviewInput`
- Commercial: `CommercialOpportunityInput`, `CommercialProductStatusInput`, `CommercialProductInput`, `CommercialQuoteLineInput`, `CommercialQuoteInput`, `CommercialQuoteDecisionInput`, `CommercialOrderStatusInput`, `CommercialOrderInput`, `CommercialSupplierInput`, `CommercialSupplierStatusInput`
- Delegation/integrations: `DelegationPreviewInput`, `ApiAnythingCallInput`, `ApiAnythingBatchInput`, `CodeEvolutionInput`
- Learning/collaboration: `OutcomeEvaluationInput`, `LearningAIProposalInput`, `ImprovementProposalInput`, `LearningDecisionInput`, `LearningNoteInput`, `HandoffCreateInput`, `HandoffDeliverInput`
- Executive/management: `ExecutivePlanInput`, `ManagerProposalInput`

Before extraction, inspect all references and preserve default values, regex patterns, bounds, and list/tuple semantics exactly. Avoid importing the API module from the schema module.

## Proposed module boundaries

Keep `api.py` as a thin composition root that creates the FastAPI app and includes routers. Extract in small, behavior-preserving stages:

| Proposed module | Route / responsibility group |
|---|---|
| `api_dependencies.py` | Runtime/store/delegation dependencies, owner authentication, login throttling, shared response helpers |
| `api_schemas.py` | Pydantic request models currently declared in the API module |
| `routers/auth.py` | Owner browser-session creation/status/logout endpoints (extracted); dashboard remains in the API composition root |
| `routers/operations.py` | Owner database backup, model-usage summary and audit-chain verification endpoints (extracted) |
| `routers/planning.py` | Plan preview and protected-action policy routes; owner-authenticated work-item queue admission and delegation preview, split across three routers to preserve original registration positions |
| `routers/system.py` | Health/readiness probes |
| `routers/catalogue.py` | Workforce roles/route preview, departments and media capabilities (extracted) |
| `routers/providers.py` | All UnoRouter settings, discovery, free-model catalogue, save/remove, and asynchronous zero-dollar inference-test routes |
| `routers/github_evolution.py` | Owner-controlled GitHub settings/access verification and draft-only code-evolution proposal/status routes (extracted) |
| `routers/integrations.py` | Owner-authenticated, read-only API Anything health, discovery and tier-1 read-call routes (extracted) |
| `routers/agents.py` | Agent listing/state and bootstrap endpoints (extracted) |
| `routers/commercial.py` | Suppliers, opportunities, products, quotes and orders |
| `routers/work.py` | Work-item CRUD/admission, worker queue/fleet, state transitions, review and deliverables |
| `routers/orchestration.py` | Delegation previews/proposals, manager/executive planning, workflow views and handoffs |
| `routers/learning.py` | Outcome evaluations, learning proposals/decisions and approved learning notes |
| `routers/evolution.py` | Reserved for future evolution capabilities not already owned by `routers/github_evolution.py` |
| `routers/portfolio.py` | Venture opportunity lifecycle and event history |
| `routers/usage_audit.py` | Model usage and audit verification |

Names are provisional. Before extraction, inspect every route's referenced globals and shared helpers; avoid circular imports by placing dependencies/schemas in lower-level modules and injecting dependencies through FastAPI.

## First route-group extraction: read-only catalogue

Four read-only endpoints were moved into `src/opencompany_app/routers/catalogue.py`: `GET /workforce/roles`, `POST /workforce/route-preview`, `GET /organization/departments`, and `GET /media/capabilities`. The router has no owner-auth dependency because these endpoints were public before extraction; no authorization policy was changed. The `WorkforceRoutePreviewInput` schema moved with its import to the router. The original route-handler block was compared with the extracted block after changing only the decorator target from `app` to `router`; the bodies and route metadata were identical. The router is included at the original position in `api.py`, preserving route registration order. Static checks confirmed 91 remaining direct route decorators plus four router decorators, all four moved paths absent from direct API registration, and the workflow route still registered once. No import or runtime check was performed.

## Health and readiness router extraction

`GET /health` and `GET /ready` were moved into `src/opencompany_app/routers/system.py`. Their handler bodies and route metadata were compared against the immediately preceding API source after changing only the decorator target from `app` to `router`; the extracted block is identical. The router imports the existing cached runtime dependency and platform metadata. It is included at the original position before the owner-backup route. The public liveness probe and database/worker readiness checks are unchanged. No authentication policy was added or removed. Static checks confirmed both paths are absent from direct API registration and remain present once in the new router. No import or runtime check was performed.

## Resolved duplicate workflow route

The duplicate `GET /work-items/{item_id}/workflow` handlers were consolidated in commit `38f0f53caccd6fb722323d00525ec6fa32f1cd92`.

Evidence used before consolidation:

- `src/opencompany_app/dashboard.py` consumes lifecycle fields including `next_action`, `prerequisites`, `dependents`, `queue`, `delegation_proposals`, `handoffs`, `deliverables`, and `counts`.
- `tests/test_opencompany_app.py` contains assertions for both response families: lifecycle/next-action fields and business-scoped manager/delegation/child-work fields.
- Both handlers used the same HTTP method and path, so retaining two registrations did not provide two independently addressable contracts.

The single handler now returns the union of both response families, retaining the business-scoped child/dependency checks. Its dependent-work list is filtered to the same business unit so the lifecycle view does not disclose other business units' work-item titles or states.

Static verification after the write fetched the file back from GitHub, confirmed exactly one matching route decorator, and confirmed source presence of all expected response-key declarations. This is not runtime verification: tests, imports, app startup, and OpenAPI generation remain deferred until 2026-12-01.

## Safe extraction sequence

1. Inventory all route decorators, schema classes, module globals, and helper references; record import dependencies.
2. Resolve the duplicate workflow route's intended contract before moving either handler.
3. [x] Extract all 36 request schemas into `api_schemas.py` without changing their definitions or validation rules.
4. [x] Extract the cached runtime singleton, runtime/store dependencies, login throttling helpers, and owner-authentication dependency into `api_dependencies.py`.
5. [x] Extract the four read-only catalogue endpoints into `routers/catalogue.py` with identical handler bodies and preserved registration position.
6. [x] Extract the GitHub settings/access and code-evolution route groups into `routers/github_evolution.py`; preserve endpoint names, methods, response shapes, dependency declarations, and registration positions.
7. [x] Extract the six owner-authenticated read-only API Anything endpoints into `routers/integrations.py`; preserve response modes, max-tier restrictions and registration position.
8. [x] Extract the five owner-authenticated agent listing/state/bootstrap endpoints into `routers/agents.py`; preserve state-transition validation, audit writes, draft-only bootstrap behavior and route registration position.
9. [x] Extract the five owner-authenticated worker queue/fleet endpoints into `routers/workers.py`; preserve zero-cost provider gates, explicit worker lifecycle controls, active-role checks and registration position.
10. [x] Extract owner-authenticated work-item listing and creation into `routers/work_items.py`; centralize the shared audit-record factory in `api_dependencies.py`. Preserve full-store dependency validation before business-scoped plan validation.
11. Continue extracting the next cohesive router group one at a time; preserve endpoint names, methods, response shapes, dependency declarations, and registration order.
12. Keep app startup/shutdown hooks and runtime ownership in the composition layer unless a dedicated lifecycle module can be introduced without changing startup semantics.
13. Continue including routers at their original registration positions; document deterministic composition order.
14. After the test deferral ends on 2026-12-01, run focused route/auth tests, inspect generated OpenAPI for duplicate operations, then run the OpenCompany test suite. Do not claim the refactor is verified before those checks.
15. Only after review and explicit owner approval consider merge, deployment, or production routing changes.

## Non-goals and safety boundaries

- No endpoint contract changes, auth weakening, permission broadening, background execution changes, database migrations, or business-unit isolation changes as part of mechanical extraction.
- No tests or CI runs before 2026-12-01, per owner instruction.
- No merge, deploy, production routing change, paid provider use, external publishing, customer commitment, or financial action is authorized by this plan.

## UnoRouter provider-route extraction

All eight owner-authenticated UnoRouter endpoints now live in `src/opencompany_app/routers/providers.py`. The first four are discovery and read-only settings endpoints:

- `POST /settings/providers/unorouter/discover`
- `GET /settings/providers/unorouter`
- `GET /settings/providers/unorouter/models`
- `GET /settings/providers/unorouter/catalog`

The extracted handler block was compared with the source block after changing only the decorator target from `app` to `router`; the bodies and route metadata match exactly. All four routes retain their explicit `require_owner_key` dependency. The settings response exposes only whether a credential is present/decryptable and the selected model; it does not return the API key. The new router is included immediately before the existing provider-save route, preserving the original registration position of the moved endpoints relative to provider mutations.

Provider save, deletion, and asynchronous inference testing were subsequently moved into the same router as one cohesive unit. The worker-stop/configuration transaction, encrypted-secret writes, in-memory background-job state, and bounded zero-dollar inference test now share the provider router module. The `_worker_autostart_enabled` helper is imported by the API startup hook from that router so startup behavior remains unchanged. No credential values, confirmation requirements, paid-fallback policy, or worker behavior were intentionally changed.

Static verification after re-fetching all four route-bearing modules found 81 direct API decorators, eight provider routes, four catalogue routes and two system routes (95 total). There were no duplicate method/path pairs across these modules. All four provider routes retain owner authentication. No imports, app startup, OpenAPI generation, tests or runtime checks were performed.

## UnoRouter mutation and inference-test extraction

The remaining four UnoRouter endpoints and their shared background-job state were moved from `api.py` into `src/opencompany_app/routers/providers.py`:

- `PUT /settings/providers/unorouter` — owner-confirmed free-model validation, worker-stop coordination, encrypted secret-vault write and runtime reconfiguration
- `POST /settings/providers/unorouter/test` — bounded asynchronous zero-dollar inference test
- `GET /settings/providers/unorouter/test/{job_id}` — owner-authenticated job polling
- `DELETE /settings/providers/unorouter` — worker-stop coordination, encrypted secret removal and runtime reconfiguration

The module now owns the in-memory job dictionary, lock and retention bound. The API startup hook imports `_worker_autostart_enabled` from the router so the existing startup decision uses the same helper. The original endpoint bodies and job lifecycle were moved without intended behavioral changes; explicit owner confirmation, free-only model checks, no paid fallback, worker-busy conflict responses, and encrypted vault usage remain in place. No inference test was invoked and no credentials were changed.

Static re-fetch verification found 81 direct API decorators, eight provider routes, four catalogue routes and two system routes (95 total). No duplicate HTTP-method/path pairs were found. All eight provider endpoints retain explicit owner authentication. The API no longer contains the provider test job state or provider mutation handlers. These checks do not prove import or runtime correctness.


## GitHub integration and code-evolution router extraction

Seven owner-authenticated endpoints now live in `src/opencompany_app/routers/github_evolution.py`, split into two routers so each group remains included at its original registration position:

- `settings_router` — `GET /settings/integrations/github-evolution`, `PUT /settings/integrations/github-evolution`, `POST /settings/integrations/github-evolution/test`, and `DELETE /settings/integrations/github-evolution`
- `evolution_router` — `GET /code-evolution/config-status`, `POST /code-evolution/proposals`, and `GET /code-evolution/pull-requests/{number}`

The module owns the route-specific imports for the GitHub client errors, code-evolution generator, request schemas, encrypted secret-vault operations, persistence audit record, and runtime/store dependencies. The original seven route-handler blocks were compared against the immediately preceding API source after normalizing only the decorator target; all seven comparisons matched exactly.

Safety boundaries remain unchanged: all seven routes explicitly require owner authentication; saving requires explicit confirmation that GitHub access is for draft PR creation only; credentials remain in the encrypted secret vault and are never echoed; proposal generation still requires both the owner-triggered zero-cost provider test and read-only GitHub access verification; and the code-evolution client creates draft pull requests only. The API response continues to report `draft: true`, `merged: false`, `deployed: false`, and owner review required. No GitHub token was changed, no access test was invoked, and no PR was created.

Static re-fetch verification found 74 direct API decorators, seven GitHub routes, eight provider routes, four catalogue routes and two system routes (95 total). No duplicate HTTP-method/path pairs were found across these route-bearing modules, and every GitHub route retains its explicit owner-auth dependency. This is static source verification only; no imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed.


## Read-only API Anything integration-router extraction

Six owner-authenticated API Anything routes now live in `src/opencompany_app/routers/integrations.py`:

- `GET /integrations/api-anything/status`
- `GET /integrations/api-anything/sites`
- `GET /integrations/api-anything/find`
- `GET /integrations/api-anything/sites/{site}/operations`
- `POST /integrations/api-anything/call`
- `POST /integrations/api-anything/batch`

The router owns the API Anything client error import, its two request-schema imports, and the existing runtime and owner-auth dependencies. All six handler bodies were compared against the immediately preceding API source after normalizing only the decorator target; all six matched exactly. The batch endpoint's function body was separately compared excluding the adjacent router-registration statement and also matched exactly.

The integration remains read-only: health/discovery and tier-1 read operations only; the call and batch handlers continue to expose the existing read-only client methods, return `mode: read-only` and `max_tier: 1`, and retain explicit owner authentication. The router is included at the former route-group location immediately before the GitHub code-evolution router. No external API call was made and no credentials were changed.

Static re-fetch verification found 68 direct API decorators, six API Anything routes, seven GitHub routes, eight provider routes, four catalogue routes and two system routes (95 total). No duplicate HTTP-method/path pairs were found across these route-bearing modules. Every API Anything endpoint retains its explicit owner-auth dependency. This is static source verification only; no imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed.


## Owner-controlled agent and workforce router extraction

Five owner-authenticated agent-management endpoints now live in `src/opencompany_app/routers/agents.py`:

- `GET /agents` — list persisted agent profiles
- `POST /agents/{agent_id}/state` — revision-checked state transition with an audit record
- `POST /agents/bootstrap` — create department-manager profiles
- `POST /agents/bootstrap-executive` — create the executive orchestrator profile
- `POST /agents/bootstrap-specialists` — create specialist profiles

The extracted module owns its narrow imports for agent state/audit records, persistence, provisioning functions, the state-change request schema, and the existing store/owner-auth dependencies. The five handler blocks were compared against the immediately preceding API source after normalizing only the decorator target; all five matched exactly.

Safety and lifecycle behavior remain unchanged: all five routes require owner authentication; bootstrap operations create draft profiles and explicitly return `execution_started: false`; they do not start worker execution. Agent activation remains a separate explicit state change, requires an eligible draft/paused transition, and refuses activation unless the profile has both a verified role and team. State changes retain expected-revision conflict handling and the atomic agent-update-plus-audit operation. The router is included immediately before the commercial-opportunity route group, at the original position.

Static re-fetch verification found 63 direct API decorators, five agent routes, six API Anything routes, seven GitHub routes, eight provider routes, four catalogue routes and two system routes (95 total). No duplicate HTTP-method/path pairs were found across the inspected route-bearing modules; all five agent routes retain explicit owner authentication. This is static source verification only; no imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed.


## Worker queue and fleet lifecycle router extraction

Five owner-authenticated worker operations now live in `src/opencompany_app/routers/workers.py`:

- `GET /workers/queue` — queue counts and readiness information, optionally scoped to a known business unit
- `GET /workers/status` — fleet status and active role-bearing profile count
- `POST /workers/start` — explicit owner-triggered worker start
- `POST /workers/stop` — explicit owner-triggered worker stop
- `POST /workers/{agent_id}/run-once` — one bounded owner-triggered internal worker cycle

All five handler blocks were compared against the immediately preceding API source after normalizing only the decorator target; the extracted block matched exactly. All five endpoints retain explicit owner authentication.

Execution safeguards remain intact: worker start and run-once both require the owner-triggered zero-cost UnoRouter test to have succeeded in the current runtime and require an eligible provider at a zero-dollar request budget. Run-once additionally requires an existing agent explicitly in ACTIVE state with a role key. The queue endpoint continues to reject unknown business-unit filters. Worker start/stop remain explicit API actions; no worker was started, stopped, or run during extraction.

The router is included at the original position between work-item enqueue and delegation-preview routes. Static re-fetch verification found 58 direct API decorators, five worker routes, five agent routes, six API Anything routes, seven GitHub routes, eight provider routes, four catalogue routes and two system routes (95 total). No duplicate HTTP-method/path pairs were found across the inspected route-bearing modules. This is static source verification only; no imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed.


## Owner-controlled agent handoff router extraction

Five owner-authenticated agent handoff lifecycle endpoints now live in `src/opencompany_app/routers/handoffs.py`:

- `POST /work-items/{item_id}/handoffs` — propose a handoff without starting execution
- `GET /work-items/{item_id}/handoffs` — list handoffs for a work item
- `POST /handoffs/{handoff_id}/accept` — owner-controlled acceptance
- `POST /handoffs/{handoff_id}/decline` — owner-controlled decline
- `POST /handoffs/{handoff_id}/deliver` — record delivery of response artifact references

The router owns the handoff payload serializer and imports only the collaboration domain operations, request schemas, runtime/store dependencies and owner-authentication dependency it needs. The router is included immediately before the executive portfolio route group, preserving the original registration position. All five routes retain explicit owner authentication, work-item existence checks, state-transition conflict handling and audit events carrying the work item's business-unit identifier. Proposal and acceptance responses continue to state that execution has not started; no worker is triggered by these routes.

Static source checks after re-fetch found 95 route registrations across the API composition root and router modules, counting the seven routes registered on the two GitHub sub-routers, with 0 duplicate method/path pairs. The handoff router contains five route decorators. These checks do not establish import, startup, OpenAPI or runtime correctness; tests and CI remain deferred until 2026-12-01. No handoff was created, accepted, declined or delivered during extraction.


## Executive planning and manager delegation router extraction

Five owner-authenticated planning/delegation endpoints now live in `src/opencompany_app/routers/orchestration.py`:

- `POST /executive/plan` — generate an owner-reviewable draft plan from an objective
- `POST /work-items/{item_id}/manager-proposal` — request an active department manager's AI-assisted team proposal
- `POST /work-items/{item_id}/delegation-proposals` — persist a deterministic manager/team proposal
- `POST /work-items/{item_id}/delegation-proposals/{proposal_id}/approve` — owner approval and child-task materialization
- `GET /work-items/{item_id}/delegation-proposals` — list proposals for a parent work item

The router preserves explicit owner authentication on all five endpoints. Executive planning still requires a known business unit and an explicitly ACTIVE CEO orchestrator, and saves draft work items with owner review required, no queue entries and no execution. Manager planning still requires the parent to be an unassigned DRAFT item and validates an ACTIVE manager and ACTIVE specialist profiles against the expected role, team and department. Proposals do not assign or enqueue work. Approval still verifies proposal-to-parent identity, draft state, manager and specialist identity, creates child work items in the parent's business unit, atomically records approval/materialization audit events, and only then applies the existing optional auto-queue policy. Auto-queue remains disabled by default and is still guarded by the strict zero-dollar eligible-provider check and role/team validation.

The three shared auto-queue helpers were moved from `api.py` to `api_dependencies.py`, so the new router and remaining enqueue/workflow code use one implementation rather than duplicating safety logic. The orchestration router is included immediately before the workflow route group, preserving registration order.

Static re-fetch verification found 95 route decorators across `api.py` and router modules, with zero duplicate HTTP-method/path pairs. The orchestration router contains five endpoints and all five retain explicit owner authentication. The three shared helper definitions now exist only in `api_dependencies.py`; the main API imports and reuses them. These are source-level checks only—not import, startup, OpenAPI, test, CI or runtime verification. Test/CI deferral until 2026-12-01 remains active. No plan or delegation proposal was created or approved; no work was queued or executed; no merge, deployment or production change occurred.


## Owner work-item lifecycle and review router extraction (2026-11-12)

Four owner-authenticated routes now live in `src/opencompany_app/routers/lifecycle.py`:

- `GET /work-items/{item_id}/workflow` — complete owner-facing lifecycle, prerequisites, business-scoped dependents, manager synthesis readiness, handoffs and deliverables
- `POST /work-items/{item_id}/review` — owner approval/rejection, atomic work-item review audit, outcome evaluation recording and the existing optional auto-queue policy
- `POST /work-items/{item_id}/transition` — guarded non-execution state transitions
- `GET /work-items/{item_id}/deliverables` — owner-authenticated deliverable listing

The four handler blocks were compared against the immediately preceding API source after normalizing only the decorator target; all four comparisons matched exactly. The workflow view still rejects cross-business delegated work/dependencies and filters dependent work to the parent business unit. Review retains its audit record, outcome evaluation, disabled-by-default auto-queue and strict free-provider/role checks. State-only transitions still cannot complete review-required work, cancel queued/running work, or enter queued/in-progress states; those remain behind the review or queue/worker pipeline. All four routes retain explicit owner authentication.

The lifecycle router is included immediately after the orchestration router, at the former workflow-route registration position. Static re-fetch found 42 direct API route decorators plus 53 router decorators (95 total), with zero duplicate HTTP-method/path pairs across the composition root and router modules. No imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed. Test/CI deferral until 2026-12-01 remains active. No work item was reviewed or transitioned; no queue action, merge, deployment or production change occurred.


## Outcome evaluation and learning router extraction

Nine owner-authenticated routes now live in `src/opencompany_app/routers/learning.py`:

- Create/list work-item outcome evaluations
- Create manual or AI-generated improvement proposals
- List proposals and record owner approve/reject decisions
- Apply an approved proposal as a durable role-learning note
- Create/list approved learning notes

All nine route handlers were moved without changing their handler source; the GitHub commit diff confirms the extracted block is removed from `api.py` and the router is included immediately after the preceding GitHub evolution router at the original registration point. Static re-fetch found 33 direct API routes plus 62 router routes (95 total), with zero duplicate HTTP-method/path pairs. All nine learning endpoints explicitly retain owner authentication.

Safeguards retained include owner-only review and decisions, evidence-backed evaluations, same-work-item deliverable references, single-business-unit evidence for AI learning analysis, zero-dollar preferred UnoRouter model requests with no paid fallback, strict model-output shape and role validation, business-scoped proposals/notes, atomic audit persistence, and the requirement that a proposal be owner-approved before it can be applied as a role note. No evaluation, proposal, model call, decision or learning note was created or applied during this extraction.

Static source checks only. No imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed. Test/CI deferral until 2026-12-01 remains active. No merge, deployment or production changes occurred.


## Commercial operations router extraction (2026-11-12)

Fifteen owner-authenticated commercial endpoints now live in `src/opencompany_app/routers/commercial.py`, split across two router instances to preserve the original registration positions:

- Twelve `/commercial/opportunities`, `/commercial/products`, `/commercial/quotes` and `/commercial/orders` routes are registered through `router` immediately after the agent router, where the original commercial opportunity routes began.
- Three `/commercial/suppliers` routes are registered through `supplier_router` at the original supplier route position after audit verification.

The fifteen handlers were moved without changes to their function bodies or route metadata; static comparison after normalizing the decorator target confirmed all fifteen match the previous API source. All fifteen explicitly retain owner authentication. The existing business rules remain: customer opportunities and catalogue records belong to one allowed commercial business unit; catalogue lookup derives scope from the opportunity's immutable business ID; quote creation derives business scope from the opportunity; quote acceptance requires an evidence reference; owner confirmations remain required for quote decisions, order creation/status and supplier verification; supplier records are restricted to the two physical-product business units; no supplier outreach, quote sending, purchase, payment or external fulfilment is triggered.

The two router instances preserve registration order rather than moving the supplier endpoints earlier with the rest of the commercial routes. Static re-fetch found 18 direct API routes plus 77 router routes (95 total), with zero duplicate HTTP-method/path pairs. All fifteen commercial routes retain explicit owner authentication. No commercial record was created or modified during extraction.

Static source checks only. No imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed. Test/CI deferral until 2026-12-01 remains active. No merge, deployment or production change occurred.


## Company-wide venture portfolio router extraction (2026-11-12)

Four owner-authenticated endpoints now live in `src/opencompany_app/routers/portfolio.py`:

- `GET /venture-opportunities` — list the company-wide opportunity register
- `POST /venture-opportunities` — save a researched opportunity without creating a business unit
- `POST /venture-opportunities/{opportunity_id}/status` — record an owner-confirmed lifecycle decision
- `GET /venture-opportunities/{opportunity_id}/events` — read the opportunity's event history

The shared `_venture_portfolio` adapter moved with the routes. All four handler blocks were statically compared against the immediately preceding API source after normalizing only the decorator target; all four matched exactly. The router is included at the original route-group position after the supplier router, preserving registration order. The API no longer imports venture portfolio schemas or implementation types directly.

The portfolio remains company-wide and distinct from operating business units. Registering or changing an opportunity does not itself create a business unit, provision accounts, spend money, publish, contact customers or launch a venture. Owner confirmation remains required for lifecycle transitions, and a launch decision is not an execution authorization.

Static re-fetch found 14 direct API route decorators plus 81 router decorators (95 total), with zero duplicate HTTP-method/path pairs. All four portfolio routes retain explicit owner authentication. No opportunity was created or modified during extraction.

Static source checks only. No imports, app startup, OpenAPI generation, tests, CI or runtime checks were performed. Test/CI deferral until 2026-12-01 remains active. No merge, deployment or production change occurred.


## Owner browser-session router extraction (2026-11-12)

Three owner-authentication session endpoints now live in `src/opencompany_app/routers/auth.py`:

- `POST /auth/session` — exchange the owner API key for a revocable browser session
- `GET /auth/session` — restore session status and rotate a missing/invalid CSRF token
- `POST /auth/logout` — revoke the current session and clear session cookies

The route handlers were statically compared against the immediately preceding API source after normalizing only the decorator target; all three matched exactly. The router is included at the original position after application startup/shutdown hooks and before the owner dashboard route. The API no longer imports the login throttling helpers or login request schema directly; the router reuses the existing shared dependency implementation in `api_dependencies.py`.

Security behavior remains unchanged: API-key comparison uses constant-time comparison; login throttling remains bounded to five failures in a 15-minute window; session cookies remain HttpOnly and SameSite=Strict; session status continues to require owner authentication; logout remains owner-authenticated; mutating browser-session requests continue to require session-bound CSRF validation and same-origin Origin/Host matching in `require_owner_key`. No credential, session, cookie or authentication setting was changed during extraction.

The API composition currently has 11 direct HTTP route decorators and 84 router HTTP route decorators (95 total). The three moved route paths were preserved; no new route behavior was introduced. The three extracted handlers all retain the existing owner-authentication dependencies where previously present. This extraction's direct checks confirmed the three source comparisons, imports and router registration; a full all-router duplicate scan was not rerun in this step, so the previous zero-duplicate inventory is not newly re-certified here.

Static source checks only. No imports, app startup, OpenAPI generation, tests, CI or runtime authentication checks were performed. Test/CI deferral until 2026-12-01 remains active. No credential, session, production configuration, merge or deployment was changed.


## Owner operational diagnostics router extraction (2026-11-12)

Three owner-only operational routes now live in `src/opencompany_app/routers/operations.py`, using two router instances to preserve their original registration positions:

- `GET /owner/backup` — consistent SQLite snapshot download, integrity-checked by the existing store backup operation
- `GET /usage/model` — durable model inference usage/cost summary, optionally scoped to one known business unit
- `GET /audit/verify` — audit event count and hash-chain verification status

The backup router is included immediately after the system health router, at the former backup route position. The diagnostics router is included at the former usage/audit position near the end of the API composition. All three handler blocks were statically compared against the immediately preceding API source after normalizing only the decorator target; all three matched exactly.

All three endpoints retain explicit `require_owner_key` dependencies. Backup still writes a temporary SQLite snapshot, removes it on failure, and schedules temporary-file cleanup after response delivery. Usage still rejects unknown business-unit filters and reads the durable usage summary. Audit verification remains read-only. No backup was generated, usage data was queried, or audit operation executed during extraction.

Static route inventory after extraction: eight direct HTTP route decorators in `api.py`, 84 routes in the previously extracted routers, and three routes in `routers/operations.py` (95 total). The three moved route definitions are absent from `api.py`; the new module contains one backup route and two diagnostics routes. All three retain owner authentication. Static checks only; no imports, app startup, OpenAPI generation, tests, CI or runtime verification were performed. Test/CI deferral until 2026-12-01 remains active. No merge, deployment, production or financial action occurred.


## Planning, queue-admission and delegation-preview router extraction (2026-11-12)

Four routes were moved into `src/opencompany_app/routers/planning.py`, using three APIRouter instances to preserve their original registration positions:

- `POST /plans/preview` and `GET /policy/protected-actions` in `planning_router`
- `POST /work-items/{item_id}/enqueue` in `queue_router`
- `POST /work-items/{item_id}/delegation-preview` in `delegation_router`

All four handler blocks were statically compared with the immediately preceding API source after normalizing only the decorator target; all four matched exactly. Router includes are placed at the original route-group positions. The API composition root no longer contains these handler definitions.

The two execution-adjacent endpoints retain explicit owner authentication. Queue admission still requires a READY item with an explicit assignee, an ACTIVE agent in the matching department, a catalogue-verified role/team, and an eligible free inference provider under a zero-dollar request budget. It admits the item to the durable queue but does not start a worker. Delegation preview remains a preview only and does not assign agents or start execution. Plan preview still validates known business units and department names and returns `execution_performed=false`; protected-action policy still derives approval requirements from the shared policy function.

A fresh static inventory across `api.py` and all route-bearing router modules found 95 route definitions, 95 unique method/path pairs and zero duplicates. Four direct route decorators remain in `api.py`; 91 route decorators are now in routers. No enqueue, delegation, worker or external action was triggered. Static checks only; no imports, app startup, OpenAPI generation, tests, CI or runtime verification. Test/CI deferral until 2026-12-01 remains active. No merge, deployment or production change occurred.
