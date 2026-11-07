# Local worker queue (first increment)

The OS now has a SQLite-backed job queue and a bounded, manually triggered worker.

## Supported job
- `build_work_packet`: validates the selected specialist through the existing work-packet builder and stores a ready-to-paste prompt. It does not call a model, use a network connection, publish content, spend money, or contact customers.

## API
- `POST /jobs` — enqueue a supported job. Optional `idempotency_key` prevents duplicate submissions with the same key.
- `GET /jobs` — inspect recent jobs.
- `POST /worker/run-once` — process at most one queued job.
- `GET /runtime` — still reports autonomous execution and external actions as disabled.

Example job body:
```json
{
  "job_type": "build_work_packet",
  "payload": {
    "agent_id": "product-trend-researcher",
    "task": "Research international demand for downloadable products",
    "context": "Prioritize evidence of actual purchases."
  },
  "idempotency_key": "research-demand-001"
}
```

## Operational limits
This is a local queue primitive, not an always-on autonomous company. The worker runs only when `POST /worker/run-once` is called or a trusted operator runs it. The queue has bounded retries (three attempts), stale-worker lease recovery, and one registered handler. It does not yet provide authentication, a background scheduler, multi-step task dependencies, or production-grade concurrency guarantees. Do not expose the worker endpoint to the public internet until authentication and authorization are implemented.
