# Roadmap

A feature is complete only when tested and its operating limits are documented.

## Phase 1 — Core foundation
- [x] FastAPI application and Python package
- [x] SQLite persistence for tasks and approvals
- [x] Human decision endpoints
- [x] Atomic, single-use approval decisions
- [x] Action-bound approvals (canonical payload, actor, resource and expiry)
- [x] CI test execution (GitHub Actions)
- [x] API-key authentication for operational endpoints outside development
- [x] Append-only audit events for task creation and approval create/decide/consume/expiry
- [ ] Authenticated distinct principals and role-based authorization
- [ ] Broader security review

## Phase 2 — Orchestration
- [x] Background worker with atomic task claims and conservative lease expiry handling
- [x] Sequential Researcher → Developer → Quality Reviewer workflow (explicit opt-in)
- [x] Persisted agent step status and automatic handoff through SQLite
- [ ] General agent registry and configurable dependency-aware DAG
- [ ] Task dependencies and assignment
- [ ] Lease heartbeat and operator-controlled recovery/reconciliation
- [ ] Durable timeout and operator-reviewed retry policy
- [ ] Worker lifecycle events in the audit trail

## Phase 3 — Memory and learning
- [x] Task-scoped persistent inter-agent memory
- [ ] Cross-task company knowledge with source attribution
- [ ] Retrieval and access controls for company memory
- [ ] Evaluation datasets and regression checks
- [ ] Continuous improvement proposals requiring human approval

## Phase 4 — Integrations
- [x] Provider-neutral OpenAI-compatible LLM adapter (no live provider configured)
- [x] MCP remote server configuration registry (no live connections or OAuth)
- [x] MCP registry changes recorded in audit events
- [ ] MCP transport client, OAuth/account connection and capability discovery
- [ ] Approval-gated MCP tool execution
- [ ] WooCommerce
- [ ] Social adapters for selected platforms with mandatory approval
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [ ] Dashboard, deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide
- [ ] Android-friendly setup and operator controls

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases. Agent graph execution is disabled by default and makes three model requests per task when explicitly enabled. Approval consumption is not yet connected to an external-action executor.

### Audit log
Audit events are written in the same SQLite transaction as the associated task, approval or MCP registry state change. The API exposes protected, newest-first pagination at `GET /audit/events`. SQLite triggers reject ordinary update and delete statements against audit rows. This is tamper-resistant against accidental application writes, not a cryptographically signed or externally immutable compliance log; a database administrator can still replace the database file. Actor labels are not independently authenticated yet.

### MCP registry boundary
The registry stores remote Streamable HTTP endpoint configuration, environment-variable *names* for credentials, and operator-declared capabilities. It never stores credential values or makes outbound network requests. A listed capability is not verified until a future MCP client performs protocol discovery. Enabling a registry entry only enables its configuration; it does not establish a connection or grant permission to execute tools. Local stdio servers, OAuth flows, endpoint health checks, and tool execution remain future work. Production connection code must add DNS/IP revalidation and per-tool approval enforcement to prevent SSRF and unsafe actions.
