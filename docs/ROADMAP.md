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
- [ ] Repair and test worker package (current worker service imports modules absent from the default-branch tree)
- [ ] Task dependencies, assignment, leases, and cancellation
- [ ] Agent interface, registry, typed inputs/outputs, and department routing
- [ ] Retry policy, timeouts, concurrency limits, execution logs, and idempotency
- [ ] Provider-neutral model adapter with zero-cost-first routing and hard cost ceilings
- [ ] Central approval service enforced for every protected action
- [ ] Optional LangGraph adapter after core queue/approval prerequisites pass (see [LangGraph decision](LANGGRAPH_ARCHITECTURE_DECISION.md))
- [ ] Background worker and scheduler with restart/recovery tests

## Phase 3 — Memory and learning
- [ ] Source-attributed company knowledge
- [ ] Retrieval and access controls
- [ ] Evaluation datasets and regression checks
- [ ] Improvement proposals requiring human approval

## Phase 4 — Integrations
- [ ] MCP server registry with allowlists, scoped credentials, timeouts, and audit logs
- [ ] Provider and tool health checks; no automatic paid fallback
- [ ] WooCommerce
- [ ] Social adapters with mandatory approval
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [ ] Dashboard, deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.
