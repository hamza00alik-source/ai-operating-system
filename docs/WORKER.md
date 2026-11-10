# Dedicated AIOS agent worker

The API and agent worker are separate processes in production. The API creates queued runs; the worker polls the same database and executes them. The worker is a long-running process, not a serverless request or scheduled function.

## Production service configuration

Create a second service from the same repository and deployment revision as the API:

- Start command: `python -m ai_os.worker`
- Runtime: persistent, always-on worker process
- Replicas: **1** (SQLite-backed queue is not configured for multiple worker replicas)
- Environment: same `AI_OS_ENV`, `AI_OS_DATABASE_URL`, model-provider configuration and encryption settings as the API
- Storage: mount the **same persistent volume at the same absolute path** used by the API's SQLite database
- Poll interval: optional `AI_OS_WORKER_POLL_SECONDS=3`

The API must not use an ephemeral local SQLite file while the worker uses a different filesystem. If the platform cannot share one persistent volume between services, do not deploy this worker design there; first migrate the queue and operational data to a shared server database.

## Runtime behavior and safety

- Development mode retains the in-process worker for local convenience.
- Non-development API mode does not start an in-process agent worker. Run this dedicated service.
- Queue claims use one atomic SQLite update to reduce duplicate execution if an API fallback worker and the dedicated worker overlap.
- On worker startup, runs left in `running` are marked failed and require an owner-requested retry. This avoids silently repeating model work.
- Graceful SIGTERM/SIGINT stops polling and lets the current task finish before exit.
- Keep one worker replica. Multi-replica locking, leases, heartbeats, and automatic crash recovery require a server database/queue and are not claimed here.
- The worker does not publish content, contact customers, spend money, connect accounts, or make commitments.

## Verification before production use

1. Confirm API and worker resolve to the exact same persistent database file.
2. Start the worker and confirm the `Dedicated worker initialized` log.
3. Queue a synthetic task in a non-customer test environment.
4. Confirm it moves from queued to running to completed and that workflow output is handed to the next department.
5. Stop the worker during an idle period and confirm it exits cleanly.
6. Restart it and verify it resumes polling. A task interrupted mid-execution must be reviewed and explicitly retried by the owner.
