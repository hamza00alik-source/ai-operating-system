# Agent registry, runtime, and execution boundaries

## What is implemented

- The company registry exposes the CEO as the single accountable orchestrator and loads the pinned Agency Agents specialist catalogue.
- The pinned read-only submodule is `vendor/agency-agents`, sourced from the owner's `agency-agents` repository. It supplies 283 specialist Markdown profiles across 18 divisions; the locally maintained CEO remains the only owner-approval gateway.
- The four validated upstream scenario runbooks are exposed through the runbook API.
- Role-specific work packets include the selected specialist profile and the company governance block. Upstream tool declarations are descriptive only; they do not grant runtime permissions.
- Company runs persist specialist steps, dependencies, assignments, reports, and status. Dependency-ready steps can be scheduled idempotently into the durable SQLite queue.
- A bounded worker can execute a specialist analysis step through the configured model adapter, authenticate the step report, evaluate it, and return the report to the CEO.
- The owner dashboard displays registered profiles, workload, company runs, approvals, evaluations, research candidates, improvement proposals, training examples, audit activity, and queue state.

## Running specialist work

The API and worker can run as separate processes. Start the API with the host's
usual ASGI command (for example, `uvicorn main:app --host 0.0.0.0 --port 8000`)
and start the durable worker with:

```bash
python -m ai_os.worker_service
```

Both processes must use the same `AI_OS_DATABASE_URL` and the same persistent
database file. For SQLite, keep both processes on the same host and local
persistent volume; do not put the database on an arbitrary network filesystem.
A process manager or hosting platform must restart the worker after host or
process failure. The worker loop polls continuously, respects the persisted
pause/stop control, refreshes runtime heartbeats, and uses bounded exponential
backoff after transient scheduler failures.

The worker initializes the database, commerce storage, control-plane registry,
credential vault, and trusted built-in read-only adapters before polling. This
is required when it runs independently of the API process.

Model execution is deliberately disabled unless the owner explicitly configures
and enables an inference backend:

- `openai_compatible`: an explicitly configured OpenAI-compatible HTTPS endpoint (HTTP is accepted only for localhost).
- `command`: an owner-configured local CLI invoked with an argument array, never through a shell. The owner must explicitly attest that the CLI's tools are disabled. This attestation is an operator assertion, not a sandbox or proof that the CLI cannot access the network.

No provider, model, endpoint, API key, or CLI command is configured by default.
There is no silent paid fallback and no bundled free inference engine. With
inference disabled, the worker remains alive and preserves queued work but will
not generate specialist reports.
 
## Scheduling and dependency handling

The scheduler inspects persisted company runs, reconciles blocked dependencies, and enqueues only pending steps whose dependencies have completed. Queue idempotency keys prevent duplicate dispatch for the same run step. The worker claims jobs using durable leases and applies bounded retry handling. A specialist step is marked blocked after its job exhausts retries.

A successful model-backed step returns a structured report to the CEO. The worker does not give the model browser, shell, account, payment, publishing, customer, or deployment tools.

## Governance and external actions

The CEO agent (registry ID `company-orchestrator`) is the single approval gateway. Specialists report to the CEO and cannot contact the owner or independently request owner approval.

The system supports signed, run-bound internal agent identities, owner-authenticated approval requests and decisions, and a server-side action gateway. However:

- Owner approval records permission for one exact action scope; it does not itself execute that action.
- The action gateway is internal server code, not a public HTTP route.
- `AI_OS_EXTERNAL_ACTIONS_ENABLED` defaults to false.
- No production external-action adapters are registered.
- Publishing, customer messaging, purchases, refunds, spending, payment changes, and deployment are not connected.
- The model adapter receives prompts only; it does not receive application tool schemas or credentials.

Keep the service local-only until TLS, rate limiting, secret rotation, role-level authorization, recovery, and an independent security review are complete. The optional CLI backend may have permissions outside this application's control.

## Learning and controlled improvement

The system records specialist evaluations and supports evidence-backed CEO improvement proposals. Instruction addenda are immutable, profile-hash-bound, screened, and require a separate owner-authenticated activation. Optional local behavior regression checks are limited signals, not proof of factual accuracy. No agent can autonomously modify its own security policy, permissions, or approval boundary.

Owner-reviewed training-example candidates can be exported as private, versioned JSONL datasets. Exporting does not train or deploy a model. No proprietary model weights or fine-tuning pipeline currently exist.

## Important distinction

The codebase provides a runnable, human-supervised agent runtime foundation. It is not yet a fully autonomous always-on AI company. Actual model execution requires an explicitly configured inference engine and an operator-started worker. Continuous background operation, production integrations, external actions, and self-hosted company model deployment remain later deployment/integration milestones.

See also:
- [CEO governance](CEO_GOVERNANCE.md)
- [Approved action gateway](ACTION_GATEWAY.md)
- [Owned company model strategy](OWN_MODEL_STRATEGY.md)
