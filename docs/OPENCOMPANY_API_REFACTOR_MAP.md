# OpenCompany API Refactor Map

Status: active refactor record. The request-schema extraction and duplicate workflow-route consolidation are implemented on the development branch; route behavior and runtime correctness remain unverified until the deferred test window.

## Scope and evidence

Inspected `src/opencompany_app/api.py` on branch `feature/opencompany-aios-unification` at blob SHA `f282b0ba05e7e703219f504eb85a2e5386255999`.

- Before duplicate-route consolidation, the module was approximately 3,360 lines and had 96 route decorators; the duplicate was removed, leaving 95 route decorators.
- `src/opencompany_app/api.py` no longer declares request models. The 36 original Pydantic request models now live in `src/opencompany_app/api_schemas.py`; static comparison against the pre-extraction API source confirms each class body is byte-for-byte identical. The API module retains 113 top-level functions (including route handlers and helpers), subject to later inventory updates.
- The application currently has only five files under `src/opencompany_app/`: `__init__.py`, `api.py`, `dashboard.py`, `provider_settings_ui.py`, and `runtime.py`.
- The module still combines application construction, runtime lifecycle, authentication dependencies, response helpers, and route handlers. Request schemas are now isolated in `api_schemas.py`.
- This is a static source inspection. No tests, imports, server startup, or runtime route-resolution checks were performed.

## Schema inventory for the next extraction

The current API module contains 36 Pydantic request models. Move them as a single mechanical extraction to `api_schemas.py` only after preserving their validation constraints and importing the exact enum/domain types they use:

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
| `routers/system.py` | Health, readiness, workforce roles/route preview, departments, media and provider status |
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
4. Extract dependency/auth helpers without changing route paths or behavior.
5. Extract one cohesive router group at a time; preserve endpoint names, methods, response shapes, dependency declarations, and registration order.
6. Keep app startup/shutdown hooks and runtime ownership in the composition layer unless a dedicated lifecycle module can be introduced without changing startup semantics.
7. Update the app composition to include routers in a documented deterministic order.
8. After the test deferral ends on 2026-12-01, run focused route/auth tests, inspect generated OpenAPI for duplicate operations, then run the OpenCompany test suite. Do not claim the refactor is verified before those checks.
9. Only after review and explicit owner approval consider merge, deployment, or production routing changes.

## Non-goals and safety boundaries

- No endpoint contract changes, auth weakening, permission broadening, background execution changes, database migrations, or business-unit isolation changes as part of mechanical extraction.
- No tests or CI runs before 2026-12-01, per owner instruction.
- No merge, deploy, production routing change, paid provider use, external publishing, customer commitment, or financial action is authorized by this plan.
