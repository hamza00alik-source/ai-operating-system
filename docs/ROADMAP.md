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
- [x] Social/video department registry and persistent content/brief workspace\n- [x] Draft-to-owner-approval lifecycle with explicit no-publish boundary\n- [ ] Metricool publishing/analytics adapter with mandatory approval\n- [ ] Canva media creation/export adapter\n- [x] Provider-neutral SQLite video-job queue, owner approval, budget gate, idempotency, and status API
- [x] Authenticated worker claim/lease protocol, heartbeat, cancellation, bounded retries, event audit, and result reporting
- [x] Optional single-GPU LongCat text-to-video worker and private MP4 artifact path
- [ ] End-to-end GPU inference verification and multi-GPU/image-to-video/continuation adapters
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [x] Owner Control Center with company overview, workforce, repository sources, tasks, approvals, discovery, and model gateway
- [ ] Deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.


## Cinecode video-engine integration
- [x] Inspect upstream Cinecode repository, documented capabilities, license, and runtime requirements
- [x] Inspect existing AIOS video queue, approval/budget gates, worker protocol, and LongCat boundary
- [x] Document Cinecode integration architecture, isolation, cost controls, and acceptance tests
- [x] Add provider-scoped worker claims and heartbeat status for Cinecode and LongCat
- [x] Enforce separate provider-specific worker credentials and bind claim identity to the authenticated provider
- [ ] Generalize video provider routing for multiple isolated workers without cross-claiming jobs
- [x] Implement allowlisted Cinecode worker capability/health reporting (GPU remains unverified until a real render)
- [x] Implement fixed-command Codex CLI adapter with workspace-write sandbox, ignored user config, ephemeral sessions, and non-Git workspace support
- [x] Implement isolated per-job workspace layout with the Cinecode kit and generated film project as sibling folders
- [x] Implement autonomous Quick-mode defaults for owner-approved jobs, final-render checks, production-report validation/upload, heartbeats, cancellation, bounded retries, and private MP4 upload/download
- [x] Enforce provider identity across every worker job action and apply private artifact aggregate quotas/free-space reserves sized for the existing 500 MB Railway volume
- [x] Add provider-isolation tests for Cinecode and LongCat job claims
- [x] Add API tests for provider-specific worker authentication, claim identity, Cinecode artifact upload, and private download
- [x] Add worker tests for path traversal, symlink exclusion, environment-secret filtering, untrusted creative briefs, MP4 validation, and production-report validation
- [x] Add allowlisted runtime capability reporting to the Owner Console (GPU remains explicitly unverified)
- [ ] Provision a dedicated OS account/container/VM and verify host-level filesystem/network isolation
- [ ] Verify one end-to-end local Cinecode render and MP4 delivery on the intended worker hardware
- [x] Add Owner Console video job creation, owner approval/rejection/cancellation, worker readiness, queue progress, and completed MP4 artifact links
- [x] Add an opt-in hardened Linux Docker worker profile with pinned Cinecode source and Codex CLI version
- [x] Keep publishing disabled; no social/platform publishing adapter is invoked by Cinecode
- [ ] Verify latest commits in CI and triage the existing full-suite OpenCompany failures
- [ ] Load-test concurrent workers and verify provider-scoped queue fairness
