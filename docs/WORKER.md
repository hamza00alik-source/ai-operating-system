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
- If the process stops after claiming a task, its status can remain `running`. There is no lease heartbeat or automatic stale-task recovery yet. Inspect and manually reconcile such tasks; do not blindly requeue them because the provider may already have received the request.
- The runtime scheduling hook currently schedules no multi-step agent graph.
- This worker cannot publish content, spend money, contact customers or modify external systems.
- Run the API and worker against the same persistent database file.
- Tests cover worker-loop behavior, default-disabled model execution, successful task persistence and provider-failure persistence. They do not validate a live external model provider.

## Next engineering gates

1. Add lease/heartbeat and safe crash recovery with idempotency protection before claiming unattended reliability.
2. Implement real multi-step agent scheduling and durable inter-agent handoff.
3. Harden approval decisions with atomic, single-use approval consumption bound to the exact proposed action.
4. Run a live provider test only after a provider endpoint and any required credentials are deliberately configured; review expected cost first.
