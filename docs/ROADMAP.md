# Roadmap

A feature is complete only when tested and its operating limits are documented.

## Phase 1 — Core foundation
- [x] FastAPI application and Python package
- [x] SQLite persistence for tasks and approvals
- [x] Human decision endpoints
- [x] CI test execution (GitHub Actions)
- [x] API-key authentication for operational endpoints outside development
- [ ] Role-based authorization and broader security review

## Phase 2 — Orchestration
- [x] Durable agent registry
- [x] Atomic queued-task claiming and assignment
- [x] Shared task handoff state in SQLite
- [ ] Agent completion/failure reporting and lease recovery
- [ ] Agent interface and provider-backed execution runtime
- [ ] Retry policy, timeouts, execution logs and supervised worker process

## Phase 3 — Memory and learning
- [x] Persistent shared memory entries with source and author metadata
- [x] Searchable memory API
- [x] Audit events for agent registration, task claims and memory writes
- [ ] Tamper-evident audit chain and access controls
- [ ] Semantic retrieval and source verification
- [ ] Evaluation datasets and regression checks
- [ ] Improvement proposals requiring human approval

## Phase 4 — Integrations
- [ ] Provider-neutral LLM adapter with explicit model selection
- [ ] WooCommerce
- [ ] Social adapters with mandatory approval
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [ ] Owner dashboard, deployment profiles and backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide
- [ ] Persistent hosted worker with restart recovery

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.
