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
- [ ] Task dependencies and assignment
- [ ] Agent interface and registry
- [ ] Retry policy, timeouts, execution logs
- [ ] Background worker and scheduler

## Phase 3 — Memory and learning
- [ ] Source-attributed company knowledge
- [ ] Retrieval and access controls
- [ ] Evaluation datasets and regression checks
- [ ] Improvement proposals requiring human approval

## Phase 4 — Integrations
- [x] Provider-neutral OpenAI-compatible LLM adapter and protected connectivity-test endpoints
- [ ] Provider-specific adapters for non-compatible APIs
- [ ] WooCommerce
- [ ] Social adapters with mandatory approval
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [ ] Dashboard, deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.
