# OpenCompany API Refactor Map

Status: inspection-only planning document. No routes, runtime behavior, authentication rules, or production configuration were changed by this map.

## Scope and evidence

Inspected `src/opencompany_app/api.py` on branch `feature/opencompany-aios-unification` at blob SHA `f282b0ba05e7e703219f504eb85a2e5386255999`.

- The module is approximately 3,360 lines and registers 96 route decorators.
- The application currently has only five files under `src/opencompany_app/`: `__init__.py`, `api.py`, `dashboard.py`, `provider_settings_ui.py`, and `runtime.py`.
- The module combines application construction, request schemas, runtime lifecycle, authentication dependencies, response helpers, and route handlers.
- This is a static source inspection. No tests, imports, server startup, or runtime route-resolution checks were performed.

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

## Confirmed issue to resolve before route extraction

There are two GET handlers registered with the exact same path:

- First registration near line 2892: `GET /work-items/{item_id}/workflow`. It returns a business-scoped workflow/delegation view and checks child/dependency business boundaries.
- Second registration near line 3119: `GET /work-items/{item_id}/workflow`. It returns a broader lifecycle view including prerequisites, dependents, queue, delegation proposals, handoffs and deliverables.

This is a route collision, not merely a naming/style concern. Depending on router registration order, one handler may shadow the other. Do not silently delete or rename either contract during a mechanical split. First establish the intended public response contract, compare frontend/client usage and OpenAPI behavior, then consolidate into one endpoint or introduce a versioned/additive route with an explicit compatibility decision. This needs runtime verification after the user's test/CI deferral.

## Safe extraction sequence

1. Inventory all route decorators, schema classes, module globals, and helper references; record import dependencies.
2. Resolve the duplicate workflow route's intended contract before moving either handler.
3. Extract schemas and dependency/auth helpers without changing route paths or behavior.
4. Extract one cohesive router group at a time; preserve endpoint names, methods, response shapes, dependency declarations, and registration order.
5. Keep app startup/shutdown hooks and runtime ownership in the composition layer unless a dedicated lifecycle module can be introduced without changing startup semantics.
6. Update the app composition to include routers in a documented deterministic order.
7. After the test deferral ends on 2026-12-01, run focused route/auth tests, inspect generated OpenAPI for duplicate operations, then run the OpenCompany test suite. Do not claim the refactor is verified before those checks.
8. Only after review and explicit owner approval consider merge, deployment, or production routing changes.

## Non-goals and safety boundaries

- No endpoint contract changes, auth weakening, permission broadening, background execution changes, database migrations, or business-unit isolation changes as part of mechanical extraction.
- No tests or CI runs before 2026-12-01, per owner instruction.
- No merge, deploy, production routing change, paid provider use, external publishing, customer commitment, or financial action is authorized by this plan.
