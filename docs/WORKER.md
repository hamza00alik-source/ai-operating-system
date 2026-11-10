# Dedicated AIOS agent worker

The API creates queued runs; the bounded worker polls the same database and executes them. On Railway, the preferred deployment is an embedded worker suite inside the existing single-replica API service, so API, queue consumers, inbox supervisor, executive supervisor and learning scheduler share the same persistent volume. A separate worker service is supported only when both services use a genuinely shared server database/queue.

## Production service configuration

### Recommended Railway configuration

- Keep the API service at **1 replica** while SQLite is the queue/database.
- Mount the existing persistent volume at `/data` on the API service.
- Set `AI_OS_EMBEDDED_WORKER=true` to start the queue consumers, department inbox supervisor, executive supervisor and six-hour learning scheduler inside the API service.
- Optional `AI_OS_WORKER_POLL_SECONDS=3`.
- Optional `AI_OS_WORKER_CONCURRENCY=2` (clamped to 1–4; default 2).
- The API and all embedded workers then use the same process configuration and `/data` volume; no second Railway service is required.

### Separate worker service (alternative)

For a future PostgreSQL/server-queue deployment, a separate persistent service can run `python -m ai_os.worker`. It must use the exact same server database and model-provider configuration as the API. Do not attach a SQLite-backed worker service unless the platform provides a genuinely shared filesystem mount; a copied or separate volume is not shared storage.

## Runtime behavior and safety

- Development mode starts the in-process worker suite for local convenience.
- Non-development API mode starts it only when `AI_OS_EMBEDDED_WORKER=true`.
- Queue claims use one atomic SQLite update, allowing a bounded number of consumer threads inside the single worker replica to claim distinct runs safely.
- Keep one worker replica. Increase concurrency only within the configured 1–4 thread limit; SQLite remains the shared queue store.
- On worker startup, runs left in `running` are marked failed and require an owner-requested retry. This avoids silently repeating model work.
- Graceful SIGTERM/SIGINT stops polling and lets the current task finish before exit.
- Keep one worker replica. Multi-replica locking, leases, heartbeats, and automatic crash recovery require a server database/queue and are not claimed here.
- An owner-started workflow automatically queues its first internal task. Each successful step queues only its immediate successor. An owner-created delegation queues its child task. The worker then processes these queued internal tasks automatically.
- Automatic execution is limited to the existing research/planning agent runtime. It has no browser, shell, filesystem, store, publishing, payment, or customer-contact capability.
- The worker does not publish content, contact customers, spend money, connect accounts, or make commitments.

## Verification before production use

1. Confirm API and worker resolve to the exact same persistent database file.
2. Start the worker and confirm the `Dedicated worker initialized` log.
3. Queue a synthetic task in a non-customer test environment.
4. Confirm it moves from queued to running to completed and that workflow output is handed to the next department.
5. Stop the worker during an idle period and confirm it exits cleanly.
6. Restart it and verify it resumes polling. A task interrupted mid-execution must be reviewed and explicitly retried by the owner.
