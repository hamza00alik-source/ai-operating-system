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
