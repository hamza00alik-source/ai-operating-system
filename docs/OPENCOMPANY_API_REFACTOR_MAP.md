# OpenCompany API Refactor Map

Status: active refactor record. The request-schema extraction, runtime/auth dependency extraction, duplicate workflow-route consolidation, read-only catalogue-router extraction, and health/readiness-router extraction are implemented on the development branch; route behavior and runtime correctness remain unverified until the deferred test window.

## Scope and evidence

Inspected `src/opencompany_app/api.py` on branch `feature/opencompany-aios-unification` at blob SHA `f282b0ba05e7e703219f504eb85a2e5386255999`.

- Before duplicate-route consolidation, the module was approximately 3,360 lines and had 96 route decorators; the duplicate was removed, leaving 95 route decorators.
- `src/opencompany_app/api.py` no longer declares request models. The 36 original Pydantic request models now live in `src/opencompany_app/api_schemas.py`; static comparison against the pre-extraction API source confirms each class body is byte-for-byte identical.
- The API now has 89 direct route decorators in `api.py`, two health/readiness routes in `routers/system.py`, and four read-only catalogue routes in `routers/catalogue.py` (95 total registrations by static composition count). Both routers are included at their original positions so registration order relative to the remaining API routes is preserved.
- The app package now includes `api_schemas.py`, `api_dependencies.py`, and a `routers/` package with `catalogue.py` and `system.py`, in addition to the composition, dashboard and runtime modules.
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
| `routers/system.py` | Remaining health/readiness and provider status routes |
| `routers/catalogue.py` | Workforce roles/route preview, departments and media capabilities (extracted) |
| `routers/providers.py` | UnoRouter settings/discovery/test lifecycle and provider candidates |
| `routers/integrations.py` | GitHub evolution settings and API-Anything read-only integration routes |
| `routers/agents.py` | Agent listing/state and bootstrap endpoints |
| `routers/commercial.py` | Suppliers, opportunities, products, quotes and orders |
| `routers/work.py` | Work-item CRUD/admission, worker queue/fleet, state transitions, review and deliverables |
| `routers/orchestration.py` | Delegation previews/proposals, manager/executive planning, workflow views and handoffs |
| `routers/learning.py` | Outcome evaluations, learning proposals/decisions and approved learning notes |
| `routers/evolution.py` | Code-evolution proposals and pull-request status |
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
6. Extract the next cohesive router group one at a time; preserve endpoint names, methods, response shapes, dependency declarations, and registration order.
7. Keep app startup/shutdown hooks and runtime ownership in the composition layer unless a dedicated lifecycle module can be introduced without changing startup semantics.
8. Continue including routers at their original registration positions; document deterministic composition order.
9. After the test deferral ends on 2026-12-01, run focused route/auth tests, inspect generated OpenAPI for duplicate operations, then run the OpenCompany test suite. Do not claim the refactor is verified before those checks.
10. Only after review and explicit owner approval consider merge, deployment, or production routing changes.

## Non-goals and safety boundaries

- No endpoint contract changes, auth weakening, permission broadening, background execution changes, database migrations, or business-unit isolation changes as part of mechanical extraction.
- No tests or CI runs before 2026-12-01, per owner instruction.
- No merge, deploy, production routing change, paid provider use, external publishing, customer commitment, or financial action is authorized by this plan.
