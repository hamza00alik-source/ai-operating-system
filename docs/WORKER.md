# Background worker

The worker is a separate process from the FastAPI web application.

## Configuration

Set these environment variables in the worker process only:

| Variable | Purpose |
|---|---|
| `AI_OS_MODEL_ENABLED` | Must explicitly be `true` to permit model requests |
| `AI_OS_MODEL_BASE_URL` | OpenAI-compatible API base URL, without `/chat/completions` |
| `AI_OS_MODEL_NAME` | Model identifier accepted by the provider |
| `AI_OS_MODEL_API_KEY` | Optional provider key; keep it secret |
| `AI_OS_MODEL_PROVIDER` | Informational provider label |
| `AI_OS_WORKER_POLL_SECONDS` | Poll interval, clamped to 1–60 seconds |
| `AI_OS_AGENT_GRAPH_ENABLED` | Set to `true` for the three-agent workflow; defaults to `false` |
| `AI_OS_DATABASE_URL` | Same persistent SQLite database used by the API |

No provider is contacted by default. The worker exits before polling unless model execution is explicitly enabled and the base URL and model are configured.

## Run as a separate process (recommended for larger hosts)

```bash
python -m ai_os.worker_service
```

Use a host process manager or platform worker service to restart the process after machine or process failure.

## Run inside the API process (single-service hosting)

For a small host that permits only one app/process, the API can manage one background worker thread:

- Set `AI_OS_WORKER_EMBEDDED=true`.
- Also set `AI_OS_MODEL_ENABLED=true`, `AI_OS_MODEL_BASE_URL`, and `AI_OS_MODEL_NAME`.
- Keep the ASGI server to one process/worker. Do not run multiple Uvicorn workers with embedded mode; each process would start its own queue consumer.
- The API lifespan starts the worker and signals it to stop during graceful shutdown. The worker publishes the same persistent heartbeat.
- The API and worker share one database path. Configure a persistent writable disk, not an ephemeral filesystem.

Embedded mode is opt-in and refuses startup if model execution is not explicitly enabled/configured. It does not make an unreliable host persistent: the hosting provider must keep the app alive and restart it after failure. For production scale, use separate API and worker services with a shared database.

## Current behavior and limits

- Processes one queued task at a time. The opt-in three-agent graph makes three sequential model requests per task.
- Uses an atomic SQLite write transaction to claim a task.
- Persists task result, error, worker ID and timestamps.
- Provider errors are not automatically retried to avoid duplicate or metered requests.
- Claims have a 15-minute lease. Expired claims become `blocked` for manual review; worker process heartbeat reports process liveness, not per-task lease renewal. There is no operator reconciliation endpoint yet.
- Agent handoffs persist in `agent_steps` and task-scoped `agent_memory`; completed steps are reused on deliberate resume. Running/failed steps are not automatically retried.
- The worker cannot publish content, spend money, contact customers or modify external systems.
- API and worker must share the same persistent database.
- Unit tests do not validate a live external model provider.

## Approval and audit safeguards

Approval requests bind the action, intended actor, target resource, structured payload and expiry. `consume_approval` atomically consumes a matching approved action but does not execute it. No external-action executor is connected yet.

The API exposes protected `GET /audit/events`. Task and approval lifecycle events are inserted transactionally; MCP registry changes are also recorded. SQLite triggers reject ordinary updates/deletes to audit rows. This is not an external immutable compliance archive.

The current API key authenticates one shared owner credential, not distinct human/agent principals. Approval `actor_id` remains caller-supplied metadata. Do not connect production credentials or external action executors until authenticated principals, per-tool approval enforcement, security review and durable backup are implemented.


## Owner-triggered model connectivity check

The Owner Control Room exposes a protected `POST /runtime/model-test` action. It sends one fixed, non-sensitive connectivity prompt and returns the provider/model label plus a short response. It does not create a task. The action is disabled at the API level unless model execution is explicitly enabled and both the endpoint and model are configured. Only an owner principal may call it.

Example experimental keyless gateway configuration (not a production recommendation):

```bash
AI_OS_MODEL_ENABLED=true
AI_OS_MODEL_PROVIDER=llmfaucet-experimental
AI_OS_MODEL_BASE_URL=https://api.llmfaucet.dev/v1
AI_OS_MODEL_NAME=auto
AI_OS_MODEL_API_KEY=free
AI_OS_AGENT_GRAPH_ENABLED=true
```

This is an optional example, not a built-in default. The public gateway documents anonymous access and a 20-request/day anonymous limit, but explicitly describes itself as experimental and warns that upstream capacity may change or disappear. Do not send private/customer data through it, do not treat it as production infrastructure, and verify its current service status before use. A successful connection test proves only that one response was returned; it does not prove three-agent execution or worker reliability.

For the first end-to-end run, use only a synthetic internal task with no customer data. Keep the graph disabled until the owner has verified a model response, then enable it deliberately and inspect each persisted agent handoff.


## MCP connection verification

The MCP registry is configuration-only until an owner explicitly tests a registered server. The owner-only `POST /mcp/servers/{server_id}/test` endpoint performs a Streamable HTTP initialize handshake and `tools/list` discovery. It does not call any discovered tool, and it reports `tool_execution_enabled: false`.

Configure the server with HTTPS and reference bearer credentials by environment-variable name (never paste secret values into the registry). The probe rejects disabled servers, missing environment variables, non-public DNS answers and redirects. The first configured credential environment variable is sent as a Bearer token. OAuth authorization flows, per-provider auth schemes, dynamic tool invocation, and credential management are not implemented yet. Tool descriptions and input schemas returned by remote servers are untrusted metadata and must not be treated as agent instructions.


### Explicitly approved MCP tool invocation

The owner-only `POST /mcp/servers/{server_id}/tools/call` endpoint can invoke one tool after consuming an exact, one-time approval. First create an approval using `POST /approvals` with:

- `action`: `mcp.tool.call`
- `resource_id`: `{server_id}:{tool_name}`
- `action_payload`: the exact object `{"server_id":"...","tool_name":"...","arguments":{...}}`

The approval actor is assigned from the authenticated owner identity. An owner must approve it through the existing approval decision endpoint. Then submit `approval_id`, `tool_name`, and the exact same `arguments` to the tool-call endpoint. The API consumes the approval atomically before making the remote call. An approval cannot be reused or altered after approval.

This is deliberately owner-triggered, not autonomous agent access. Tool names must still be advertised by the server and required/unknown argument keys are checked against its declared input schema. Remote tool execution can have real external effects; inspect the tool description and exact arguments before approving. Tool schemas are untrusted metadata, and full JSON Schema validation, OAuth flows, per-tool policy classification, and automatic agent invocation are not implemented. The endpoint is not a sandbox for malicious MCP servers.
