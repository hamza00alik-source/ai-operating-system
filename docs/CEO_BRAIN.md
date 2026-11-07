# CEO Brain: objective-to-company-plan layer

## What it does

The CEO planning endpoint converts one company objective into a durable company
run. It selects specialist roles, creates bounded tasks, records why each
workstream was selected, and establishes dependencies for later dispatch.

- `POST /ceo/plan`: create a CEO plan from an objective, context, and constraints.
- `GET /ceo/plans/{run_id}`: retrieve the saved plan and linked execution state.
- `GET /company-runs/{run_id}`: inspect specialist assignments and progress.
- `POST /company-runs/{run_id}/steps/{step_key}/dispatch`: generate a packet for a ready step.
- `POST /company-runs/{run_id}/steps/{step_key}/report`: submit a specialist report to the CEO.

## Governance

The CEO Agent remains the accountable agent. Specialist assignments are internal
work only. No specialist can request owner approval or perform external actions.
Publishing, external messages, spending, purchases, refunds, customer
commitments, paid services, and production/security/financial changes remain
blocked until the CEO requests explicit owner approval.

## Planning method and limitations

Version `deterministic_rules_v1` uses transparent keyword rules to select
baseline company workstreams and add conditional engineering, design, finance,
or security review. The response includes a decision log and the exact planner
version. This is not an LLM, it does not reason semantically, and it does not
invoke any model/API. A later model-backed CEO planner must be introduced behind
a provider-neutral adapter, evaluated against this rules baseline, and kept
behind the same CEO governance gateway.

Creating a plan does not dispatch work. Dispatch creates a local specialist
work packet only; it does not call a model, external tool, or publish anything.
