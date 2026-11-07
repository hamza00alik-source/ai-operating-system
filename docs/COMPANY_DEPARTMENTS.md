# Company departments

The AI Operating System is intended to operate as a coordinated multi-department
company. The CEO Agent (`company-orchestrator`) remains accountable for all
company work and is the only owner-approval gateway.

## Department directory

The machine-readable charter is `company/departments.json`. The owner API
exposes it through:

- `GET /company/departments` — all department charters, manager-profile
  resolution, specialist counts and current readiness labels.
- `GET /company/departments/{department_id}` — one department.

The initial organization contains Research & R&D, Product Development,
Technology & Engineering, Design & Creative, Marketing & Audience Growth,
Sales & Revenue Growth, Store & E-commerce, Customer Support, Finance &
Administration, Operations & Project Management, Quality/Security/Compliance,
People & Agent Management, and Data/Analytics/Learning.

## Department workload and CEO overview

The coordination APIs expose actual workload from persisted company runs and durable manager plans:

- `GET /company/overview` — CEO-level roll-up of department assignments, pending/assigned/completed/blocked counts, company-run status and governance flags.
- `GET /company/departments/{department_id}/workload` — one department's proposed manager, manager source division, specialist count, recent assigned steps, reports, linked worker-job status, and manager-plan counts (delegated/reviewed/blocked).

Workload membership is derived from the configured manager specialist's source division in the pinned agent library. This is an initial routing convention, not an independently staffed department boundary; review manager/source-division mapping before relying on it for staffing or performance decisions. Only steps already present in company runs appear. Empty workload does not mean the department is inactive outside this system.

These endpoints are owner-authenticated and read-only. They do not assign new work, invoke a model, or run manager agents. The CEO overview is an operational visibility layer, not yet an autonomous coordination loop.

## Manager delegation and review workflow

The durable manager coordination endpoints now provide a first execution contract:

- POST /company-runs/{run_id}/departments/{department_id}/plan — invokes the configured model with that department manager's pinned Agency Agents profile and asks it to create up to eight specialist tasks.
- GET /company-runs/{run_id}/department-plans — lists persisted department plans and their status.
- POST /company-runs/{run_id}/departments/{department_id}/review — after every delegated task is completed or blocked, asks the manager to assess the reports and record a CEO-facing summary.
- POST /ceo/review/{run_id} now includes saved department-manager reviews in the CEO's consolidated review input.

Plans are stored in SQLite and create durable pending company-run steps. Assignments are limited to enabled specialist profiles in the manager profile's source division; task keys, dependencies, and plan size are validated. Manager reviews are recommendations and escalations only. They cannot approve actions or bypass the CEO/owner approval gateway.

These routes require a configured model provider; no model is configured or invoked by default. Creating a plan queues tasks but does not dispatch workers. The shared worker runtime still needs to be enabled to execute them. Manager review is only available after all delegated steps have terminal reports. This is request-driven coordination, not yet an always-running manager process or autonomous CEO loop.

## What the directory does — and does not do

This is an organization and routing foundation. It resolves a named specialist
profile as each department's proposed manager and reports available specialist
profiles. It does **not** create 13 independent persistent manager processes,
budgets, private integrations, schedules, or autonomous decision authority.
A manager assignment is not evidence that the manager is running.

The current runtime still uses the shared durable worker and configured
provider-neutral inference adapter. Model execution is opt-in and no model is
configured by default. Department-specific workflows, delegated budgets,
store writes, social publishing, customer messaging, payments and deployment
remain disconnected or approval-gated.

## Governance

- Specialists report to their assigned workflow and the CEO; they do not approve
  their own external actions.
- Publishing, external messages, customer commitments, spending, refunds,
  payments, production changes and security-sensitive changes require the
  applicable CEO escalation and explicit owner approval.
- Unknown actions fail closed.
- The directory is read-only. It cannot change roles, permissions, integrations
  or production settings.

## Next implementation stages

1. Add department-specific work queues, manager review contracts and workload
   reporting on top of the existing durable queue.
2. Give each department its own measurable service-level and quality metrics.
3. Add connector adapters incrementally, starting with read-only store visibility
   and draft-only actions.
4. Add persistent scheduling and worker supervision on the chosen host.
5. Verify cross-department execution end-to-end before enabling any external
   side effects.
