# Roadmap

A feature is complete only when tested and its operating limits are documented.

## Phase 1 — Core foundation
- [x] FastAPI application and Python package
- [x] SQLite persistence for tasks, approvals, discovery scans, and candidates
- [x] Human decision endpoints
- [x] CI test execution (GitHub Actions)
- [x] API-key authentication for operational endpoints outside development
- [x] Owner dashboard for discovery and guarded model requests
- [x] Additive SQLite migration for discovery worker leases
- [x] Atomic discovery scan claiming, lease renewal, and stale-lease recovery
- [x] Remove broken imports from the legacy worker entry point
- [ ] Role-based authorization and broader security review
- [ ] End-to-end test against a configured live free provider (requires owner credentials and explicit approval)

## Phase 2 — Orchestration
- [x] Initial GitHub discovery scan queue, candidate persistence, metadata evaluation, and separate worker
- [x] First persistent Research Analyst agent using the guarded model gateway
- [x] Owner dashboard controls and saved run history for the Research Analyst
- [ ] Durable general-purpose agent runtime and resumable multi-step execution
- [ ] LangGraph orchestration integrated with existing approvals and persistence
- [ ] Dashboard UI for agent runs, approvals, logs, and owner review
- [ ] Task dependencies and assignment
- [ ] Agent interface and registry
- [ ] Bounded retries, timeouts, and execution logs for agent tasks

## Phase 3 — Memory and learning
- [ ] Source-attributed company knowledge
- [ ] Retrieval and access controls
- [ ] Evaluation datasets and regression checks
- [ ] Improvement proposals requiring human approval

## Phase 4 — Integrations
- [ ] MCP server registry and permission-scoped tool execution
- [ ] WooCommerce
- [ ] Social adapters with mandatory approval
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [ ] Dashboard, deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide
- [ ] Production observability and incident recovery

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.

The discovery worker uses a 15-minute renewable SQLite lease. Expired leases can be reclaimed by another worker after a process crash. This is a lightweight single-host queue design, not a distributed multi-host queue or a substitute for a production message broker.
