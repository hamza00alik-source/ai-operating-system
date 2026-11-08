# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this repository is a starter foundation, not a fully autonomous company. External AI providers, background workers, ecommerce, and social integrations are not connected yet.

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
- Persist tasks, approval records, agent steps and task-scoped inter-agent handoffs in SQLite.
- Optionally run the Researcher → Developer → Quality Reviewer workflow with `AI_OS_AGENT_GRAPH_ENABLED=true`; it is disabled by default and makes three sequential model requests per task.
- Inspect task-scoped memory and workflow status through the protected `/tasks/{task_id}/memory` and `/tasks/{task_id}/steps` endpoints.
- Register and manage remote MCP Streamable HTTP endpoint configurations through protected `/mcp/servers` endpoints. Credential environment-variable names are recorded; secret values are not stored.
- Health endpoint.
- API-key protection for operational endpoints outside development.

### MCP registry (configuration only)
Use `POST /mcp/servers` with a name, HTTPS endpoint, optional credential environment-variable names, and operator-declared capabilities. Use `GET /mcp/servers` to list entries and `POST /mcp/servers/{id}/enabled?enabled=true|false` to toggle a configuration. Entries report `connection_status: not_connected` until a real MCP transport and OAuth/account workflow is implemented. Enabling an entry does not connect to it or execute tools. The registry rejects non-HTTPS, localhost/private-IP endpoints and credential values supplied where environment-variable names are expected.

In development, operational endpoints are open for local testing. In staging/production, set `AI_OS_ENV=production` and a strong private `AI_OS_API_KEY`. Send it in the `X-API-Key` header. The app refuses to start in non-development mode if the key is missing. Keep `/health` public for uptime checks.

Approval requests are bound to a structured action payload, intended actor, target resource and expiry. The service supports atomic single-use consumption through `consume_approval`; no external executor is connected to it yet. The current `actor_id` is caller-supplied metadata, not independently authenticated identity. Legacy approval rows cannot authorize execution. Do not connect production credentials until distinct principal authentication, audit logging and executor-level safeguards are implemented and reviewed.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).
