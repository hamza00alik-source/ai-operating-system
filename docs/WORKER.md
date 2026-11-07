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

## Current limits

- Processes one queued task at a time.
- Uses an atomic SQLite write transaction to claim a task.
- Persists task result, error, worker ID and timestamps.
- Provider errors mark a task failed. They are not automatically retried, to avoid accidental repeated or metered model requests.
- The runtime scheduling hook currently schedules no multi-step agent graph.
- This worker cannot publish content, spend money, contact customers or modify external systems.
- Run the API and worker against the same persistent database file.
