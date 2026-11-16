# OpenCompany worker deployment notes

The API and worker are separate processes. The worker must use the exact same
persistent SQLite database file as the API. Do not run this worker on a
serverless runtime, an ephemeral filesystem, or a host that cannot keep a
process alive between requests.

## Process command

Install the project with `pip install -e .`. Start the OpenCompany API using
`opencompany-api` (or `python -m opencompany_app.server`). Start the worker as
a separate long-running process using:

```bash
python worker_main.py
```

The launcher adds the repository's `src/` directory to Python's import path.
The project also exposes `opencompany-worker` when installed with
`pip install -e .`.

## Required private environment

- `OPENCOMPANY_DATABASE_PATH`: same absolute, persistent SQLite path for API
  and worker.
- `OPENCOMPANY_WORKER_ENABLED=true`: explicit opt-in; default is disabled.
- `OPENCOMPANY_UNOROUTER_API_KEY`: API key from the user's own account.
- `OPENCOMPANY_UNOROUTER_FREE_MODEL`: account-callable chat model ending in
  `:free`.
- `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true`: set only after the owner checks
  the current model pricing, quotas, and account billing settings.
- Optional `OPENCOMPANY_WORKER_POLL_SECONDS`: idle polling interval (1–60).

Never commit the key or put it in a GitHub file. The worker will not start
unless a file-backed database and confirmed zero-cost provider are configured.
It uses a fixed HTTPS UnoRouter endpoint and has no paid fallback.

## Operational boundaries

- Run one worker instance. A SQLite-backed 120-second startup guard rejects a
  second recently active process.
- `GET /workers/service-status` is owner-authenticated and reports durable
  process heartbeats, processed-task counts, and stale state.
- The queue lease is 15 minutes; the provider request timeout is at most
  60 seconds. Queue lease renewal is not implemented.
- A task must already be assigned to an active specialist and admitted to the
  owner-controlled queue. Results remain in owner review; the worker cannot
  publish, contact customers, spend money, or make external commitments.
- Process supervision, backups, persistent storage, and provider account
  eligibility must be validated on the actual host before production use.
- This repository change does not create a hosting service, configure secrets,
  start the worker, or authorize production deployment.
