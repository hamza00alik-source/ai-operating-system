# OpenCompany deployment guide

This guide describes deployment prerequisites for the OpenCompany API and its
optional separate worker process. It does not mean a host has been provisioned
or that a production deployment has been performed.

## Hosting requirements

Choose a host that provides all of the following:

- A persistent writable filesystem or managed SQLite volume.
- A long-running Python 3.11+ process for the API.
- If background execution is required, a second supervised long-running Python
  process for the worker.
- The same persistent SQLite file mounted at the same absolute path for both
  processes.
- Private environment-variable configuration and HTTPS.
- A restart policy and access to application logs.

A serverless runtime or ephemeral filesystem is not suitable for the current
SQLite-backed worker design. Do not assume that a preview deployment or a
single-process free hosting plan can run the API and worker reliably.

## Install and start the API

From the repository root:

```bash
python -m pip install -e .
export OPENCOMPANY_DATABASE_PATH=/absolute/persistent/path/opencompany.sqlite3
export OPENCOMPANY_OWNER_API_KEY="set-a-long-random-private-value"
opencompany-api
```

Alternatively, use `python -m opencompany_app.server` after installing the
project. The API listens on `0.0.0.0` and uses the host's `PORT` value,
defaulting to 8000.

Do not use `main.py` as the OpenCompany entry point; it remains the legacy
AIOS starter.

## Required API environment

| Variable | Requirement |
|---|---|
| `OPENCOMPANY_DATABASE_PATH` | Absolute path to persistent SQLite storage |
| `OPENCOMPANY_OWNER_API_KEY` | Strong private owner API key |

Optional asset configuration:

| Variable | Requirement |
|---|---|
| `OPENCOMPANY_ASSET_STORAGE_ROOT` | Private persistent directory for business assets |
| `OPENCOMPANY_CLAMAV_SOCKET` | Protected local ClamAV Unix socket; without it scans fail closed |

Never commit secrets, API keys, customer data, or private files to GitHub.
Use the hosting provider's private environment-variable panel.

## Optional separate worker

The worker is disabled by default. Enable it only after the API is using the
persistent database and an owner has verified a currently free provider model
and account billing settings.

Set these private environment variables for the worker and API:

- `OPENCOMPANY_DATABASE_PATH`: exactly the same file path used by the API.
- `OPENCOMPANY_UNOROUTER_API_KEY`: key from the owner's own account.
- `OPENCOMPANY_UNOROUTER_FREE_MODEL`: callable chat model ID ending in
  `:free`.
- `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true`: owner assertion after checking
  current model pricing, quota, and billing settings.
- `OPENCOMPANY_WORKER_ENABLED=true`: explicit worker opt-in.
- Optional `OPENCOMPANY_WORKER_POLL_SECONDS`: idle polling interval (1–60).

Start one separate worker process with `opencompany-worker` or
`python worker_main.py`. See [OPENCOMPANY_WORKER.md](OPENCOMPANY_WORKER.md)
for the worker's process guard, monitoring endpoint, and operational limits.

A `:free` model identifier and owner confirmation do not guarantee permanent
availability or unchanged provider terms. No paid fallback is implemented.
If no provider is configured, the worker refuses to start and no inference is
attempted.

## Smoke tests before production

1. `GET /health` returns HTTP 200.
2. `GET /ready` returns HTTP 200 after the owner key and persistent database
   are configured.
3. The owner can authenticate and open `/owner`.
4. Create a test work item and specialist profile, restart the API, and verify
   both remain in SQLite.
5. If the worker is enabled, verify `GET /workers/service-status` with owner
   authentication and confirm the heartbeat advances.
6. Queue a harmless test task, verify its deliverable enters owner review, and
   confirm that no external action is performed.
7. Test database backup and restore before adding customer or supplier data.
8. Confirm logs do not contain credentials, private customer data, or secrets.

## Production boundaries

The current worker is single-instance only. Queue leases expire after 15
minutes; the provider request timeout is bounded to at most 60 seconds, but
queue lease renewal is not implemented. Multi-replica execution, process
supervision, backups, disaster recovery, and a full security review remain
required before production operation.

No marketplace, ecommerce, social publishing, payment movement, external
customer communication, or unattended production changes should be enabled
until their own connectors, permissions, and approval workflows are implemented
and reviewed.
