# Deployment guide (Enzonic Python hosting)

This guide prepares the existing FastAPI application for a small always-on
Python host. It does not imply that a server has been provisioned or deployed.

## Hosting profile to verify

Before deploying, recheck the current Enzonic panel for free-tier capacity,
RAM, CPU, storage, idle behavior, and persistence. Free capacity and terms can
change. Do not rely on an old screenshot or prior plan description.

## Repository settings

- Runtime: Python 3.11 (the version used by CI).
- Main file: `main.py`.
- Install dependencies from `requirements.txt` (or `pip install -e .`).
- Clone the repository with Git submodules enabled (`git clone --recurse-submodules`); the pinned Agency Agents profile library is required for the full specialist catalogue.
- Bind to `0.0.0.0` and the port supplied by the host (`PORT`, default 8000).
- API start command: `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`.
- Worker start command (a separate always-on process): `python -m ai_os.worker_service`.

The API and worker must share the same `AI_OS_DATABASE_URL` and persistent
SQLite file. For SQLite, run both processes on the same host and local
persistent volume. Configure the host/process manager to restart the worker
after failure. A web-only deployment without the worker will not continuously
process company tasks.

## Required environment variables

Set these privately in the hosting panel. Never commit real values.

| Variable | Value |
|---|---|
| `AI_OS_ENV` | `production` |
| `AI_OS_API_TOKEN` | Strong random secret, at least 32 characters |
| `AI_OS_DATABASE_URL` | `sqlite:////absolute/path/on/persistent-storage/ai_os.db` |
| `AI_OS_AGENT_SIGNING_KEY` | Strong private signing secret for internal agent identities |
| `AI_OS_CREDENTIAL_ENCRYPTION_KEY` | Private Fernet key for encrypted credential storage |

Optional model configuration (keep inference disabled until a provider is
verified): `AI_OS_MODEL_ENABLED=false`, `AI_OS_MODEL_BACKEND=openai_compatible`,
`AI_OS_MODEL_BASE_URL`, `AI_OS_MODEL_NAME`, and `AI_OS_MODEL_API_KEY`.
Enabling inference can contact a third-party provider and may incur costs.
Review provider terms and pricing first. Never commit keys or tokens.

For compatibility with the original deployment preparation commit, the
application also accepts `AI_OS_API_KEY` as an alias when
`AI_OS_API_TOKEN` is unset. If both are set, `AI_OS_API_TOKEN` takes
precedence. Send the secret in either `Authorization: Bearer <secret>` or
`X-API-Key: <secret>` header. The public health and dashboard shell routes
are exceptions; dashboard data APIs remain protected.

The database path above is a template, not a confirmed Enzonic mount path.
Replace it with the actual persistent writable directory displayed or
documented by the host. SQLite parent directories are created automatically,
but an ephemeral directory will still lose data after replacement/redeploy.

## Initial smoke tests

After deployment, verify:

1. `GET /health` returns HTTP 200.
2. `GET /runtime` without an owner key returns HTTP 401.
3. `GET /runtime` with the correct owner key returns HTTP 200.
4. Create a test task and verify it remains after an app restart.
5. Verify the SQLite database is on persistent storage.
6. Confirm logs contain no API keys, provider secrets, or customer data.

Do not connect WooCommerce, social accounts, payment credentials, autonomous
publishing, or external actions until authentication, persistence, backups,
and audit logging have been independently verified.

## Resource limitations

Treat a small free host as suitable only for the lightweight API and modest
worker activity. Do not host large language models or multiple heavy agent
processes on it. Model calls and Exa research remain disabled unless separately
configured. Review provider pricing and data handling before enabling them.
