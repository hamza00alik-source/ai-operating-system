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
- [ ] End-to-end execution audit trail

## Phase 3 — Memory and learning
- [x] Task-scoped persistent inter-agent memory
- [ ] Cross-task company knowledge with source attribution
- [ ] Retrieval and access controls for company memory
- [ ] Evaluation datasets and regression checks
- [ ] Continuous improvement proposals requiring human approval

## Phase 4 — Integrations
- [x] Provider-neutral OpenAI-compatible LLM adapter (no live provider configured)
- [ ] MCP provider registry and account-connection workflows
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
