# OpenCompany AIOS — unified product architecture

**Status:** Canonical product and architecture boundary.

## Product decision

OpenCompany and AIOS are one system, not two products:

- **OpenCompany** is the product identity and the company operating environment.
- **AIOS** is the intelligence and execution engine inside OpenCompany.
- **OpenCompany AIOS** is the single product name used by the package, API, owner console, and documentation.

There is one application, one deployment unit, one owner identity and approval boundary, one shared persistence/runtime composition, and one release lifecycle. Do not create a second AIOS server, dashboard, database, or agent registry.

## Code ownership

| Layer | Canonical implementation | Responsibility |
|---|---|---|
| AIOS engine | `src/opencompany_core` | Domain contracts, workforce, planning, execution, memory/learning, model gateway, durable queue, collaboration, research and policy controls |
| Application/runtime | `src/opencompany_app` | FastAPI application, composition root, API workflows, worker lifecycle and owner console |
| Process entrypoint | `main.py` | Starts the unified `opencompany_app.api:app` application |
| Persistence | OpenCompany core SQLite store | Shared transactional persistence for the unified runtime |
| Product identity | `src/opencompany_core/platform.py` | Canonical product ID, display name and version |

The engine and application are separate code layers, not independently deployable products. New AIOS capabilities belong in `opencompany_core` and are exposed through the same OpenCompany application.

## Legacy boundary

`src/ai_os` is legacy reference code. It is not the active AIOS engine, must not be imported by the new OpenCompany runtime, and must not be merged wholesale into `opencompany_core`. Reimplement only independently specified capabilities that are still needed, with new tests and security review. Reference repositories may inform high-level product requirements, never supply copied implementation code or prompts.

## Company operating model

The platform can support multiple legitimate businesses. Each commercial business has its own identity, work scope, customer and supplier records, product catalogue, credentials, finances, integrations and approval context. Shared company services may provide capabilities, but may not silently mix business records or fulfilment.

The initial business units are:

- `physical-agency` — third-party physical supplier representation and agreed agency fees.
- `physical-brand` — the owner's separately operated physical-product brand.
- `digital-products` — independently owned digital products and downloadable assets.
- `core` — internal platform and company-wide governance only; not a commercial business.

Additional ventures may be added as separately isolated business units after owner approval. A task or opportunity does not automatically create a business, account, storefront or external commitment.

## Governance and cost boundaries

- Owner approval is required before spending, purchases, publishing, external customer/supplier contact, contracts, financial actions, production deployment or binding commitments.
- Model routing must fail closed when an explicitly owner-confirmed zero-cost provider is unavailable. No paid model fallback.
- External integrations are disabled until credentials, scopes, business isolation and approval controls are implemented and reviewed.
- Generated drafts and queued work are not evidence of external completion.
- Audit records must identify the actor, action, target, business scope and outcome.

## Definition of done for unification

- The distribution name, API title and owner console identify one product: OpenCompany AIOS.
- `main.py` and the Vercel entrypoint start the same API application.
- The application composes the AIOS engine from `opencompany_core`.
- The legacy `ai_os` package is not imported by the active runtime.
- There is no second deployment, dashboard, database or parallel agent registry.
- Documentation consistently describes one product with layered internals.
- Tests and deployment checks pass before any production release.

## Current implementation status

This change establishes the canonical identity and architecture boundary. It does not claim that every future AIOS capability, marketplace connector, external workflow or production-readiness check is complete. CI/tests are intentionally not run under the repository's current testing deferral; verify them when that instruction expires or is changed. No production deployment or merge is performed by this change.
