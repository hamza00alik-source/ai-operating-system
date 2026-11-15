# OpenCompany AI Brain: orchestration and model routing

## Purpose

OpenCompany uses a provider-neutral orchestration layer rather than depending on
one model vendor or treating a chat model as the whole workforce. The system
separates planning, model selection, execution, review, and owner authorization.

## Existing execution foundation

The current OpenCompany application already contains:
- a durable, lease-fenced worker queue and supervised worker fleet;
- specialist role profiles and department/team capability catalogues;
- persisted delegation proposals and peer handoffs;
- business-scoped learning notes and prerequisite deliverables;
- a provider-neutral model gateway and usage ledger;
- review-required deliverables, owner approvals, and audit records.

These components remain the execution and governance foundation. The new
`opencompany_core.orchestration` module adds deterministic planning and routing
primitives; it does not replace those components.

## Owner API surface

The planner is exposed through the owner-authenticated OpenCompany API:
- `GET /orchestration/brain/status` reports whether the existing gateway currently
  exposes any eligible zero-cost provider, without returning credentials.
- `POST /orchestration/brain/plan-preview` validates a bounded team dependency
  graph and returns deterministic parallel execution batches.

The preview endpoint is intentionally non-executing: it does not call a model,
create queue entries, materialize delegation, or activate agents. It is suitable
for the owner console to inspect a plan before using the existing manager
proposal and owner-approval workflow. API tests cover authentication, cycle and
business-scope rejection, zero-cost status reporting, and the no-execution
contract.

## New orchestration primitives

### Task-aware model routing

A routing request identifies:
- task kind (research, analysis, engineering, creative, operations, review);
- task complexity (routine, standard, complex, critical);
- estimated context size;
- required capabilities;
- business-unit scope; and
- the request budget.

A model candidate must be explicitly marked `FREE_CONFIRMED`, have a zero-dollar
per-request ceiling, satisfy the task/capability requirements, have enough
context capacity, and meet the minimum reasoning-effort threshold.

Selection is deterministic:
- routine and standard work prioritizes latency, then quality;
- complex and critical work prioritizes quality and reasoning effort, then
  configured priority.

If no candidate qualifies, routing fails closed. Paid or unknown-billing
candidates are never used as fallback. The routing decision records the selected
provider/model, the reason, the business scope, and the number of candidates
considered.

The module is provider-neutral. It does not invent model capabilities or
automatically treat a provider as free; the application must supply trustworthy
candidate metadata from an explicitly verified configuration.

### Bounded team plans

An `AgentTeamPlan` is a deterministic dependency graph of specialist tasks.
Validation rejects duplicate task IDs, missing dependencies, cycles, invalid
business-unit scope, excessive parallelism, and excessive retries. The planner
returns stable topological execution batches constrained by the configured
parallel-agent limit.

Every task remains review-required. Planning does not:
- provision or activate agents;
- create durable queue entries;
- approve delegation proposals;
- start workers or call a model;
- bypass business-unit isolation;
- authorize external tools or actions.

The existing owner-reviewed delegation and worker queue paths remain the only
execution path.

## Cost and safety defaults

- Request budget: USD 0.
- Paid provider fallback: prohibited.
- Unknown billing status: ineligible.
- Model calls: none during planning or routing.
- External actions: not available to the planner.
- Deliverables: review required.
- Worker startup: remains behind existing owner-triggered provider verification
  and explicit autostart controls.

## Integration status

This commit adds the pure orchestration policy module and unit tests. The
existing gateway and worker execution path are not yet automatically selecting
among multiple model candidates from a live provider catalogue. To complete
that integration, the application must expose owner-verified candidate
capability metadata, attach routing decisions to model usage/audit events, and
have the worker request a route before calling the gateway. This should be done
without weakening the gateway's own zero-cost checks.

No provider has been activated, no credentials have been added, no paid API
has been called, and no production configuration has been changed.

## Verification

The module is covered by tests for:
- latency-first and quality/reasoning-first routing;
- paid/unknown billing rejection;
- capability, task-type, and context filtering;
- zero-cost request budgets;
- dependency batching, cycle detection, and unknown dependencies;
- mandatory review and business-scope validation.

A successful unit test run does not by itself prove live multi-agent execution,
provider availability, production readiness, or commercial outcomes.
