# Owner dashboard

The responsive owner dashboard is served by the FastAPI application at `/dashboard`. It is an operational view with an owner-controlled research review inbox; it does not start agents, dispatch work, or execute external operations.

## What it displays

- Agent catalogue: enabled profiles returned by `GET /agents`. A registered profile is not evidence of a running AI process.
- Per-agent workload: pending, assigned, completed, and blocked run steps grouped by the assigned `agent_id`.
- Progress percentage: completed steps divided by all tracked steps for that agent. Agents with no tracked steps show 0% and an idle state.
- Last recorded activity: newest `updated_at` timestamp among the agent's tracked run steps.
- Company runs: persisted run status and completed-step counts from `GET /company-runs`.
- Worker queue: local packet-builder and specialist execution jobs from `GET /jobs`.
- Owner approvals: recorded approval requests from `GET /approvals`. This panel is informational; the trusted CEO approval-request gateway remains closed until server-verified CEO identity is available.
- Research review inbox: agent-proposed and manually entered candidates from \`GET /knowledge?status=candidate\`; the owner can open the source and accept or reject each candidate. No agent can approve its own research.
- Recent audit activity: meaningful audit events from \`GET /audit\`; routine read-request events are filtered to keep the feed useful.
- Runtime safeguards and model readiness: `GET /runtime` and `GET /models/status`.

The dashboard refreshes automatically every 30 seconds while its browser tab is visible. The Refresh button can also be used at any time.

## Authentication and deployment

The HTML shell at `/dashboard` is public so the browser can load it. All operational data endpoints remain behind the owner API-token middleware. The owner token is held in tab-scoped `sessionStorage`, sent in the Authorization bearer header, and cleared by Sign out. Do not share the token or commit it to the repository.

For local development, generate a token and export it before starting Uvicorn:

```bash
export AI_OS_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf 'Owner token: %s\n' "$AI_OS_API_TOKEN"
uvicorn ai_os.api:app --reload
```

Use HTTPS when exposing the service beyond a trusted local environment. Do not deploy the dashboard publicly until a secure hosting and secret-management configuration is in place.

## Current limitations

- The worker can execute bounded specialist analysis only when an inference engine is explicitly configured; it is not a fleet of 283 independent model instances.
- Progress reflects stored workflow records, not live model tokens, CPU activity, or independent agent heartbeats.
- Agent profile count is not the count of active agents.
- Approval records can be inspected, but this dashboard does not make approval decisions or trigger external actions.
- Model execution is disabled by default. Ecommerce, social publishing, spending, customer commitments, and other external actions remain disconnected and require separate implementation and owner approval.

## Verification

The API tests verify the public dashboard shell, owner-token protection on data APIs, dashboard data-source wiring, owner-token protection, candidate review controls, the model-status endpoint, and per-agent progress and auto-refresh features.


## Backup limitation

SQLite backup creation and integrity verification are available as an explicit local helper (`ai_os.db_backup.create_database_backup`). The dashboard does not schedule backups, upload them off-host, or restore databases. Backups contain private company data and must be stored with restricted access. Stop all application writers before any manual restore operation.
