# Durable worker queue

The company runtime uses a SQLite-backed durable queue with idempotent enqueue,
atomic job claims, worker leases, bounded retries, stale-lease recovery, and a
separate supervised worker process.

## Supported jobs

- `build_work_packet`: create a local role-specific task packet.
- `execute_company_step`: execute an assigned specialist report through the
  explicitly configured model adapter.
- `review_department_plan`: run the manager's review after delegated department
  tasks have completed or been blocked.

Model inference remains disabled unless an owner explicitly configures and
enables an adapter. A running worker does not imply that a model is configured
or that a provider is reachable.

## API

- `POST /jobs` — enqueue a supported job. An optional `idempotency_key`
  prevents duplicate submissions.
- `GET /jobs` — inspect recent queue records.
- `POST /worker/run-once` — process at most one queued job (operator/test use).
- `GET /runtime` — inspect runtime status and execution controls.
- `POST /company-runs` — create a dependency-ordered company workflow.
- `GET /company-runs/{run_id}` — inspect step reports and overall status.

The background worker calls the scheduler and processes the durable queue
continuously. Start it with:

```bash
python -m ai_os.worker_service
```

The API and worker must share the same `AI_OS_DATABASE_URL` and persistent
SQLite file. For SQLite, run them on the same host/local persistent volume.
Configure the hosting platform or process manager to restart the worker after
failure. The worker refreshes leases during long jobs, reports heartbeats, and
backs off after transient scheduler failures.

## Recovery and safety

Queue jobs use idempotency keys, atomic claims, bounded retries, and lease
expiry recovery. A specialist job that exhausts retries is marked blocked, and
dependent steps are blocked rather than run with missing prerequisites.
Completed dependency reports are included in downstream work packets as
untrusted handoff context.

The worker has no default browser, shell, payment, publishing, customer-message,
or deployment access. Built-in agent tools are read-only and capability-gated.
Remote MCP discovery is metadata-only until an owner-approved execution mapping
and its safety controls are implemented. Sensitive external actions remain
behind owner approval and are not enabled by default.

A healthy worker process is not proof of a live model provider, production
storefront connection, or end-to-end commercial operation. Verify those
integrations independently before enabling business workflows.
