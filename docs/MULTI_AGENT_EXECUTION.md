# CEO-coordinated company execution

The company-run layer stores multi-step work plans in SQLite, validates specialist
assignments and dependency graphs, creates specialist work packets only after
their prerequisites are complete, and stores reports/evidence for the CEO.

## API

- `POST /company-runs`: create a company run with named steps and dependencies.
- `GET /company-runs` and `GET /company-runs/{run_id}`: inspect durable run state.
- `POST /company-runs/{run_id}/steps/{step_key}/dispatch`: create a specialist work packet when dependencies are complete.
- `POST /company-runs/{run_id}/steps/{step_key}/report`: store a completed/blocked report and evidence.

## Current behavior

- The CEO Agent is the accountable company orchestrator.
- Specialists are assigned by stable agent ID and their imported profile is
  embedded in the generated work packet.
- A step can be dispatched only after every declared dependency is completed.
- Reports are stored with evidence links and blockers and are marked as reported
  to the CEO.
- Invalid agents, duplicate keys, unknown dependencies, and cyclic graphs fail
  validation.
- The API remains behind the existing owner authentication middleware.

## Important limitations

This is durable workflow coordination, not 283 running AI agents. Dispatch
creates a local prompt packet; it does not invoke a model, send a prompt to an
external service, or perform outside actions. Reports are submitted through the
owner-authenticated API and are not cryptographically attributable to a
particular specialist. A future model/runtime adapter must preserve the CEO
approval gateway and add actor-level authorization before autonomous use.

No scheduler, always-on host, paid API, external integration, or automatic
publishing is introduced by this layer.
