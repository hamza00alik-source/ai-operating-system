# Background worker

The worker is a separate process from the FastAPI web application.

## Configuration

Set these environment variables in the worker process only:

| Variable | Purpose |
|---|---|
| `AI_OS_MODEL_ENABLED` | Must explicitly be `true` to permit model requests |
| `AI_OS_MODEL_BASE_URL` | OpenAI-compatible API base URL, without `/chat/completions` |
| `AI_OS_MODEL_NAME` | Model identifier accepted by the provider |
| `AI_OS_MODEL_API_KEY` | Optional provider key; keep it secret |
| `AI_OS_MODEL_PROVIDER` | Informational provider label |
| `AI_OS_WORKER_POLL_SECONDS` | Poll interval, clamped to 1–60 seconds |
| `AI_OS_DATABASE_URL` | Same persistent SQLite database used by the API |

No provider is contacted by default. The worker exits before polling unless model execution is explicitly enabled and the base URL and model are configured.

## Run

Install the project, then start the worker as a separate supervised process:

```bash
python -m ai_os.worker_service
```

Use a host process manager or platform worker service to restart the process after machine or process failure. The in-process loop backs off after transient scheduler/database errors; it is not a replacement for host-level supervision.

## Current behavior and limits

- Processes one queued task at a time.
- Uses an atomic SQLite write transaction to claim a task.
- Persists task result, error, worker ID and timestamps.
- Provider errors mark a task failed. They are not automatically retried, to avoid accidental repeated or metered model requests.
- Claims carry a 15-minute lease by default. When a later worker pass detects an expired lease, it moves the task to `blocked` for human review; it never automatically requeues the task because the provider may already have received the request. Older `running` rows without lease metadata are checked using `started_at`.
- There is no lease heartbeat or operator reconciliation endpoint yet. A task that runs longer than its lease may be blocked; a late worker cannot overwrite that blocked state. Review the task before any manual retry.
- The runtime scheduling hook currently schedules no multi-step agent graph.
- This worker cannot publish content, spend money, contact customers or modify external systems.
- Run the API and worker against the same persistent database file.
- Tests cover worker-loop behavior, default-disabled model execution, successful task persistence, provider-failure persistence, expired-lease blocking and legacy stale-task recovery. Approval decisions are also tested for concurrent single-use behavior. Tests do not validate a live external model provider.

## Next engineering gates

1. Add lease heartbeats and an operator-controlled reconciliation path; define provider idempotency before allowing retries.
2. Integrate the action-bound approval consumer into each external-action executor, with authenticated actor identity and durable audit records.
3. Implement real multi-step agent scheduling and durable inter-agent handoff.
4. Run a live provider test only after a provider endpoint and any required credentials are deliberately configured; review expected cost first.


## Action-bound approval safeguards

Approval requests created through the current API must specify:
- `actor_id`: the intended actor identity for the proposed action.
- `resource_id`: the exact target resource (for example, a specific store or wallet).
- `action_payload`: the structured parameters that will be executed.
- `expires_in_seconds`: an expiry window (60 seconds to 7 days; default 15 minutes).

The service canonicalizes the action, actor, resource and payload and stores a SHA-256 fingerprint. Decisions are single-use and expire. Before an integration executor performs an external action, it must call `consume_approval` with the same approval ID and exact action parameters. Consumption is atomic; changed parameters, a different actor/resource, expired approvals and repeated consumption are rejected.

Important boundaries:
- `consume_approval` only consumes authorization; it does not execute the external action.
- No external-action executor is wired to this consumer yet. Therefore this is not permission to connect production credentials or perform live actions.
- `actor_id` is currently caller-supplied metadata. The current single API-key authentication does not independently authenticate distinct human or service identities.
- Existing approval rows from before this migration have no action fingerprint and cannot be consumed for execution; create a new approval for any future action.
- The API key is shared owner authentication, not a role/identity provider. Add distinct authenticated principals before multi-user or multi-agent production use.
