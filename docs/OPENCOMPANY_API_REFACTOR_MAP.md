# OpenCompany API Refactor Map

Status: active refactor record. The request-schema extraction, runtime/auth dependency extraction, duplicate workflow-route consolidation, catalogue and system router extractions, complete UnoRouter provider-router extraction, GitHub integration/code-evolution router extraction, read-only API Anything integration-router extraction, and owner-authenticated agent/workforce router extraction are implemented on the development branch; route behavior and runtime correctness remain unverified until the deferred test window.

## Scope and evidence

Inspected `src/opencompany_app/api.py` on branch `feature/opencompany-aios-unification` at the latest API blob SHA `7135eff3060c938e7b8401bed82b0a01eb4539cc`.

- Before duplicate-route consolidation, the module was approximately 3,360 lines and had 96 route decorators; the duplicate was removed, leaving 95 route decorators.
- `src/opencompany_app/api.py` no longer declares request models. The 36 original Pydantic request models now live in `src/opencompany_app/api_schemas.py`; static comparison against the pre-extraction API source confirms each class body is byte-for-byte identical.
- The API now has 63 direct route decorators in `api.py`, five agent/workforce routes in `routers/agents.py`, six read-only API Anything routes in `routers/integrations.py`, seven GitHub integration/code-evolution routes in `routers/github_evolution.py`, eight UnoRouter routes in `routers/providers.py`, two health/readiness routes in `routers/system.py`, and four read-only catalogue routes in `routers/catalogue.py` (95 total registrations by static composition count). The routers are included at their original route-group positions.
- The app package now includes `api_schemas.py`, `api_dependencies.py`, and a `routers/` package with `catalogue.py`, `providers.py`, `system.py`, `github_evolution.py`, `integrations.py` and `agents.py`, in addition to the composition, dashboard and runtime modules.
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
| `routers/auth.py` | Session creation/status/logout and owner dashboard/backup endpoints |
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
9. Continue extracting the next cohesive router group one at a time; preserve endpoint names, methods, response shapes, dependency declarations, and registration order.
10. Keep app startup/shutdown hooks and runtime ownership in the composition layer unless a dedicated lifecycle module can be introduced without changing startup semantics.
11. Continue including routers at their original registration positions; document deterministic composition order.
12. After the test deferral ends on 2026-12-01, run focused route/auth tests, inspect generated OpenAPI for duplicate operations, then run the OpenCompany test suite. Do not claim the refactor is verified before those checks.
13. Only after review and explicit owner approval consider merge, deployment, or production routing changes.

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
