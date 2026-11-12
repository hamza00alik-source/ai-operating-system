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
- [x] Owner-triggered workflow creation; first step queued and downstream steps blocked by default
- [x] Dependency-gated task execution and automatic next-step handoff after successful completion
- [ ] Workflow-level artifact aggregation, cancellation, parallel branches, and specialist-specific deliverable schemas
- [ ] Task dependencies and assignment
- [x] Static specialist registry sourced from Agency Agents
- [ ] Live agent runtime and worker registry
- [ ] Retry policy, timeouts, execution logs
- [x] In-service discovery polling worker (single service)
- [ ] Durable agent worker queue, scheduler, leases, and retries

## Phase 3 — Memory and learning
- [ ] Source-attributed company knowledge
- [ ] Retrieval and access controls
- [ ] Evaluation datasets and regression checks
- [ ] Improvement proposals requiring human approval

## Phase 4 — Integrations
- [ ] Provider-neutral LLM adapter
- [ ] WooCommerce
- [x] Social/video department registry and persistent content/brief workspace\n- [x] Draft-to-owner-approval lifecycle with explicit no-publish boundary\n- [ ] Metricool publishing/analytics adapter with mandatory approval\n- [ ] Canva media creation/export adapter\n- [ ] Video generation adapter with verified free-cost gate
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [x] Owner Control Center with company overview, workforce, repository sources, tasks, approvals, discovery, and model gateway
- [ ] Deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.
