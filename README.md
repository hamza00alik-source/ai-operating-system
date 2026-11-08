# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this repository is a starter foundation, not a fully autonomous company. External AI providers, live MCP sessions, ecommerce, and social integrations are not connected yet.

## Principles
- Human approval before external or consequential actions.
- No spending, publishing, customer commitments, or production changes without explicit approval.
- Provider-independent architecture.
- Local-first development; SQLite is the default.
- Never commit secrets or customer data.

## Quick start
Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn ai_os.api:app --reload
```

Open http://127.0.0.1:8000/docs.

## Current starter capabilities
- Create and list work tasks.
- Create, list, approve, and reject approval requests.
- Persist tasks, approvals, agent steps and task-scoped inter-agent handoffs in SQLite.
- Optionally run the Researcher → Developer → Quality Reviewer workflow with `AI_OS_AGENT_GRAPH_ENABLED=true`; it is disabled by default and makes three sequential model requests per task.
- Inspect task-scoped memory and workflow status through protected `/tasks/{task_id}/memory` and `/tasks/{task_id}/steps` endpoints.
- Register and manage remote MCP Streamable HTTP endpoint configurations through protected `/mcp/servers` endpoints. Credential environment-variable names are recorded; secret values are not stored.
- Read append-only task, approval and MCP configuration audit events through protected `GET /audit/events`.
- API-key authentication with distinct principals and role-based access outside development.

### Authentication and roles
For a single-owner deployment, set a strong private `AI_OS_API_KEY`; it is treated as the `owner` principal. For multiple principals, set `AI_OS_API_KEYS` to a JSON object whose keys are API tokens and whose values contain a stable `principal_id` and one role: `owner`, `operator`, `agent`, or `viewer`. Example (use unique, strong secrets and keep this value outside source control):

```bash
export AI_OS_API_KEYS='{"replace-with-owner-secret":{"principal_id":"owner","role":"owner"},"replace-with-viewer-secret":{"principal_id":"auditor","role":"viewer"}}'
```

The mapping is read from the environment at request time. Never commit real tokens. The legacy `AI_OS_API_KEY` remains supported as an owner key. If both settings are configured, both sets of keys are accepted.

- `owner`: full access, including approval decisions and MCP configuration changes.
- `operator`: create tasks and approval requests; read operational data.
- `agent`: create tasks; read operational data.
- `viewer`: read-only access.

Audit actor IDs for API-created tasks and approvals are derived from the authenticated principal, not the caller-supplied `actor_id` field. Approval decisions are owner-only and record the deciding principal. This is API-key identity, not end-user OAuth or fine-grained per-resource tenancy.

### MCP registry (configuration only)
Use `POST /mcp/servers` with a name, HTTPS endpoint, optional credential environment-variable names, and operator-declared capabilities. Use `GET /mcp/servers` to list entries and `POST /mcp/servers/{id}/enabled?enabled=true|false` to toggle a configuration. Entries report `connection_status: not_connected`. Enabling an entry does not connect to it or execute tools. The registry rejects non-HTTPS, localhost/private-IP endpoints and credential values supplied where environment-variable names are expected.

### Audit events
`GET /audit/events?limit=100` returns newest events first (maximum 500). Pass `before_id` from the last event to fetch an older page. Audit rows are inserted alongside state changes, and SQLite triggers reject ordinary update/delete operations. This is not an externally immutable compliance archive; protect and back up the database.

In development, operational endpoints use a local development owner principal for convenience. In staging/production, configure at least one API key using `AI_OS_API_KEY` or `AI_OS_API_KEYS`. Send it in the `X-API-Key` header. The app refuses to start in non-development mode if neither setting is present. Keep `/health` public for uptime checks.

Approval requests are bound to a structured action payload, intended actor, target resource and expiry. The service supports atomic single-use consumption through `consume_approval`; no external executor is connected to it yet. Legacy approval rows cannot authorize execution. Do not connect production credentials until an external-action executor and broader security review are implemented.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

See [docs/ROADMAP.md](docs/ROADMAP.md).
