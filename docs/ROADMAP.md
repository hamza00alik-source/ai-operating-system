# OpenCompany roadmap

A capability is marked complete only when its implementation is present in this
repository and the relevant tests pass. A repository feature is not considered
production-ready merely because code or a deployment preview exists.

## Current status

OpenCompany is an independently designed, human-supervised operating-system
foundation. It is not yet a fully autonomous or production-operated company.
The current implementation is built around OpenCompany-owned role definitions,
SQLite persistence, explicit owner approval, and fail-closed execution controls.

## Latest orchestration increment — verified by GitHub Actions

Implemented on the current draft PR branch and verified by GitHub Actions:

- CEO-triggered manager coordination can ask active department managers to
  prepare specialist-team delegation proposals for unassigned draft work.
- Proposals remain drafts and require owner approval before assignment or child
  task materialization.
- The orchestration status endpoint reports dependency and specialist blockers.
- The owner-triggered readiness pass advances only drafts whose dependencies
  are complete and whose assigned specialist is active and role-matched.
- The readiness pass does not admit queue work or start execution.
- Regression tests cover authorization, CEO activation, dependency blockers,
  active-specialist checks, repeat-safe advancement, and no queue side effects.

The first Actions run for this increment reported 207 passed and one failed
because the work-item response omitted its revision field. The serializer was
corrected in commit `20f4cf9caeeb8b21187e69f51a06c17bd7a2afca`. The corrected
branch passed the full GitHub Actions suite on commit
`7b78fbc1d715f3c001bee69ed2b5935f116d2179`: **208 passed, 1 warning**.
OpenCompany core tests passed, and Vercel prebuilt build validation passed.
These are CI/build checks, not a live production deployment.

## Completed and covered by repository tests

### Core application and business boundaries
- [x] OpenCompany FastAPI application, API launcher, owner console, and Python package.
- [x] Owner authentication, session protections, request security headers, and owner-only operational routes.
- [x] SQLite persistence for work items, delegation proposals, usage, business records, assets, agent profiles, and worker presence.
- [x] Three distinct business units: physical-products agency, own physical-products brand, and digital products.
- [x] Append-only hash-linked work-item audit history and verification.
- [x] Private asset upload streaming, bounded reads, checksum verification, and private filesystem storage support.
- [x] Owner-confirmed ClamAV scan workflow with fail-closed scanner handling and scan-event history.
- [x] No public asset download route; clean assets still require separate delivery approval.

### OpenCompany workforce
- [x] Original OpenCompany catalogue with 10 departments, 10 department managers, one CEO orchestrator, and 500 specialist roles (511 role definitions total).
- [x] 100 department teams; five named specialist playbooks in each department's first team (50 total).
- [x] Capability-based templates for the remaining 450 specialist positions.
- [x] Department-aware routing previews and role/capability matching.
- [x] Durable SQLite agent registry; profiles and owner-controlled active/paused/draft state survive runtime restarts.
- [x] Owner-controlled provisioning and role-state changes with revision checks.

### Supervised orchestration and execution
- [x] Work-item creation, assignment, dependency validation, and owner-controlled queue admission.
- [x] CEO draft plans and delegation proposals with owner review before child work is created or queued.
- [x] Idempotent queue admission and explicit retry of failed work.
- [x] Delegation child materialization uses stable proposal-derived IDs so an approval retry can reuse children created before an interrupted proposal save.
- [x] Durable queue leases, 15-minute abandoned-lease recovery, and stale-worker fencing.
- [x] Role and assigned-agent identity checks before work is claimed or executed.
- [x] Gateway-backed specialist draft generation; outputs enter owner review and do not trigger external actions.
- [x] Owner-triggered single-task execution endpoint.
- [x] Optional separate `opencompany-worker` process, persistent process heartbeats, owner-only worker status, and a transactional single-instance startup guard.
- [x] Worker only processes work already admitted to the owner-controlled queue and assigned to an active specialist.

### Model gateway and operating safety
- [x] Provider-neutral gateway interface with explicit zero-cost eligibility checks.
- [x] UnoRouter OpenAI-compatible adapter restricted to owner-confirmed model IDs ending in `:free`.
- [x] Fixed HTTPS endpoint, bounded response size and request timeout, token usage recording, and no paid fallback.
- [x] Provider configuration is fail-closed: absent credentials or owner confirmation means no eligible provider.
- [x] No automatic publishing, external customer contact, purchases, payments, or customer commitments.

### Developer experience and verification
- [x] Separate `opencompany-api` and `opencompany-worker` launch commands.
- [x] OpenCompany quick-start and worker deployment documentation.
- [x] GitHub Actions full test suite: 208 passed, 1 warning on commit `7b78fbc1d715f3c001bee69ed2b5935f116d2179`.
- [x] OpenCompany core tests passed on that commit.
- [x] Vercel prebuilt build validation passed; this is not a production deployment.

## Remaining engineering work

### Orchestration maturity
- [x] Owner can explicitly reject a draft delegation proposal with a required rationale; rejection is persisted and creates no child tasks or queue entries.
- [ ] Full CEO-led execution loop that plans, delegates, evaluates, and advances work across departments.
- [ ] Parallel branch scheduling, workflow-level artifact aggregation, cancellation, and specialist-specific deliverable schemas.
- [ ] Durable execution logs, bounded retry/backoff policy, per-task timeouts, and owner-visible failure recovery.
- [ ] Idempotent deliverable persistence across a process crash between saving a result and completing its queue lease.
- [ ] Queue lease renewal/heartbeat for long-running model calls and work.
- [ ] Multi-worker and multi-replica support; current worker is intentionally single-instance.

### Intelligence, memory, and quality
- [ ] Source-attributed company knowledge base with retrieval and per-business access controls.
- [ ] Shared team context and long-lived memory with retention, review, and provenance controls.
- [ ] Evaluation datasets, role-specific quality rubrics, and regression benchmarks for generated work.
- [ ] Better model routing and live validation of current free-model availability, quotas, privacy terms, and commercial-use permissions.
- [ ] More individually authored specialist playbooks beyond the first 50 named templates.

### Integrations and business operations
- [ ] Official, permissioned CRM, email, marketplace, ecommerce, analytics, and support adapters.
- [ ] Owner-approved customer enquiry and order workflows with auditable handoff boundaries.
- [ ] Product catalogue, pricing, inventory, supplier, and fulfilment workflows for each business unit.
- [ ] Payment-status verification only; no autonomous movement of funds.
- [ ] Publishing and customer communication remain disabled until an explicit approval workflow and connector-specific safeguards are implemented.

### Production readiness
- [ ] Select and validate a host that supports a persistent writable database and a separately supervised long-running worker process.
- [ ] Configure encrypted backups, restore tests, monitoring, log retention, and disaster recovery.
- [ ] Configure the owner's API key and a personally verified zero-cost provider through private hosting environment variables.
- [ ] Run an end-to-end live inference and worker test against the owner's own account without paid fallback.
- [ ] Complete role-based authorization, threat modelling, dependency review, and an independent security review.
- [ ] Verify deployment, restart recovery, worker supervision, and database persistence on the actual production host.

## Explicit operational limits

The worker is opt-in and will not start without a file-backed shared database,
an explicit enable flag, and a confirmed zero-cost provider. Its provider
request timeout is shorter than the 15-minute queue lease, but queue lease
renewal is not implemented. The single-instance guard is not a substitute for
a production process supervisor.

No provider credentials are stored in the repository. No live provider request,
worker process, customer action, purchase, publishing action, or production
deployment is performed by these code changes. The PR remains draft and
unmerged until the owner reviews and authorizes those steps.
