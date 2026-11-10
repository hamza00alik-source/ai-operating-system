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
- [ ] Workflow-level artifact aggregation, cancellation, parallel branches, and specialist-specific deliverable schemas
- [x] Business-scoped internal department inbox and message persistence
- [x] Sequential workflow handoffs create recipient-department inbox messages
- [x] Owner-supervised department task delegation with automatic child-run queueing
- [x] Bounded parallel worker consumers (1–4 threads in one replica) and automatic execution of owner-authorized workflow/delegation tasks
- [ ] Autonomous inbox interpretation and independent task creation
- [ ] Task dependencies and assignment
- [x] Static specialist registry sourced from Agency Agents
- [x] Three-stage task collaboration: lead specialist, independent collaborator, and CEO integration/QA review
- [ ] Autonomous department inbox interpretation and multi-agent task planning
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
- [x] Source-attributed research capture and business-scoped retrieval (URL evidence retained separately from learned memories)
- [ ] Evaluation datasets and agent-quality regression benchmarks
- [x] Guarded code-evolution writer: allowlisted source/test/docs edits in isolated GitHub branches and draft PRs
- [ ] Configure a least-privilege GitHub token and enable code-evolution flag in Railway; validate CI and owner review
- [x] Autonomous six-hour telemetry evaluation and evidence-labelled improvement proposals requiring owner review

## Phase 4 — Integrations
- [x] Provider-neutral LLM gateway and free-only provider failover
- [ ] WooCommerce live store connection and operational sync (read-only account verification code exists; owner store URL/API credentials required)
- [ ] Social account connections and publishing workflows (read-only OAuth adapters exist; provider app credentials and owner OAuth authorization required)
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [x] Owner Control Center with company overview, workforce, repository sources, tasks, approvals, discovery, and model gateway
- [ ] Deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.

## Current deployment snapshot (2026-11-10)
- [x] Supabase baseline applied to the empty AIOS project: 22 tables, 23 indexes, RLS enabled on all 22 tables.
- [x] `rls_auto_enable()` direct EXECUTE revoked from public/API roles; event trigger preserved.
- [x] Autonomous brain evaluation deployed: every six hours, per business environment, measuring run outcomes and creating owner-reviewed improvement proposals.
- [ ] Run the owner-authenticated Railway-to-Supabase `SELECT 1` test and verify the target before any production database switch.
- [ ] Back up and migrate existing Railway SQLite data before switching to Supabase; keep the current database active until a verified rollback is available.
- [ ] Configure external provider app credentials and owner OAuth connections for social, marketplace and WooCommerce accounts.
- [ ] Add verified free LLM provider credentials/models; agent execution otherwise waits safely when no eligible provider is connected.

## Guarded autonomy policy
- [x] AI may collaborate internally, generate code proposals, and open isolated draft PRs when explicitly configured.
- [ ] AI-generated code changes are not auto-merged or deployed; production release remains owner-controlled.
- [ ] External write permissions remain disabled until each platform connection is authenticated and scoped; publishing, customer contact, purchases, payments, and commitments require explicit owner approval.
