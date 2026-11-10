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
- [x] Initial GitHub discovery scan queue, candidate persistence, metadata evaluation, and separate worker
- [x] Dashboard UI for scan status, evidence, and owner review
- [x] Persistent owner browser sessions (HttpOnly, Secure, SameSite=Strict; 14-day expiry)
- [x] Agency workforce catalog: 283 specialist definitions across 18 source categories
- [x] Company department registry: 12 business departments mapped to source specialist categories
- [x] Department-aware task routing from company department IDs to specialist catalogue pools
- [x] Owner-visible inventory of 12 reference/workforce repositories
- [ ] Worker lease/claim safety for multiple worker instances
- [ ] CEO-led agent orchestration beyond discovery
- [ ] Load specialist instruction files into bounded execution contexts
- [x] Initial department workflow templates with persisted workflow instances and ordered task dependencies
- [x] Owner-authorized workflow creation; first step automatically enters the agent queue and downstream steps remain blocked by default
- [x] Dependency-gated execution; successful handoffs automatically queue the next department
- [ ] Workflow-level artifact aggregation, cancellation, parallel branches, and specialist-specific deliverable schemas\n- [x] Business-scoped internal department inbox and message persistence\n- [x] Sequential workflow handoffs create recipient-department inbox messages\n- [x] Owner-supervised department task delegation with automatic child-run queueing\n- [x] Bounded parallel worker consumers (1–4 threads in one replica) and automatic execution of owner-authorized workflow/delegation tasks
- [ ] Autonomous inbox interpretation and independent task creation
- [ ] Task dependencies and assignment
- [x] Static specialist registry sourced from Agency Agents
- [ ] Live agent runtime and worker registry
- [ ] Retry policy, timeouts, execution logs
- [x] In-service discovery polling worker (single service)
- [x] Durable agent worker queue with atomic claims and bounded in-process concurrency
- [ ] Shared server database, worker leases/heartbeats, multi-replica scheduling, and crash-safe retries

## Phase 3 — Memory and learning
- [x] Business-scoped task assignment for physical agency, own physical brand, and digital products
- [x] Exact-scope persistent memory retrieval; no cross-business fallback
- [x] Business-tagged experience capture and owner-approved lessons
- [x] Backward-compatible migration assigning legacy tasks/memories to internal core
- [ ] Full business-level isolation for research sources, credentials, customers, finance, integrations, and dashboard access
- [ ] Source-attributed company knowledge
- [ ] Evaluation datasets and regression checks
- [ ] Improvement proposals requiring human approval

## Phase 4 — Integrations
- [ ] Provider-neutral LLM adapter
- [ ] WooCommerce
- [ ] Social adapters with mandatory approval
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [x] Owner Control Center with company overview, workforce, repository sources, tasks, approvals, discovery, and model gateway
- [ ] Deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.
