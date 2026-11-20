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

## Recently implemented — CI verified, live runtime acceptance pending

- [x] Mobile-friendly owner control center: secure owner sign-in, company refresh, workforce provisioning and state controls, draft work creation, department visibility, worker/queue status, model usage, and finance-ledger visibility.
- [x] Task workflow detail view with prerequisite/dependent visibility and deliverable inspection.
- [x] Persisted specialist-team proposal creation, owner approval/rejection, and child-task materialization through existing guarded APIs.
- [x] Owner review of generated deliverables with explicit approve/reject rationale and evaluation recording.
- [x] CEO readiness advancement, separate owner-controlled queue admission, and explicit worker start/stop/single-task controls. Worker start and queue admission fail closed unless a confirmed zero-cost provider is eligible.
- [x] Business-unit-scoped owner-written memory creation and inspection, source attribution, and read-only integration/credential registry visibility. Agent memory writes remain disabled.
- [x] Worker execution now includes only the current business unit's active owner-written memories and completed prerequisite deliverables; manager roles receive explicit synthesis guidance.
- [x] Readiness advancement, queue admission, and worker execution reject incomplete or cross-business prerequisites.
- [x] One bounded CEO coordination cycle can optionally draft a plan, request manager delegation proposals, and advance eligible work. It never queues or executes work; owner approval remains separate.
- [x] Owner console supports business-memory history inspection and owner-confirmed deactivation; agent-written memory remains disabled.
- [x] Finance controls include business/currency-scoped monthly expense limits, append-only budget-decision history with rationale, monthly ledger status, and owner-entered statement reconciliation with discrepancy detection. Budgets are monitoring thresholds, not spend authorization; reconciliation is not bank-connected.
- [x] Integration registry supports owner approve/reject decisions with append-only event history. Approved records remain `approved_pending_connection`; no external connector is activated.
- [x] An isolated OpenCompany Docker staging target uses its own persistent volume, private staging secrets, and disabled worker/provider configuration. GitHub Actions builds the image, checks readiness/owner access, and verifies a work item survives container restart.
- [x] Business-unit-scoped internal records for suppliers, customers, draft products, owner activation, and order lifecycle through owner-attested payment evidence and fulfillment status. These are internal records only; no customer contact, payment, stock reservation, listing publication, or fulfillment action is executed.
- [ ] Full CEO workflow aggregation, role-specific quality evaluation, parallel scheduling, cancellation, lease renewal, and durable retry/backoff remain outstanding.
- [ ] Memory still needs retrieval/search relevance, richer provenance review, retention policies, and role-scoped access beyond the current same-business worker context.
- [ ] Finance still needs verified bank/payment-status data adapters, invoice/payout matching, refunds/fees/COGS treatment, and complete profit reporting. Current statement balances are owner-entered inputs.
- [ ] Official CRM, email, marketplace, ecommerce, analytics, and support adapters remain unimplemented. Integration approval is a permission-review record only, not a live connection. Inventory reservation, supplier purchase orders, external listings, customer enquiries, payment processor verification, and fulfillment execution remain unimplemented.
- [ ] Hosted staging is not provisioned. The verified Docker staging run is isolated CI/local staging, not an internet-accessible hosted environment. A persistent hosted service, backup/restore, HTTPS, secrets, monitoring, and owner-approved cost review remain required.
- [ ] Live preview acceptance remains blocked by the legacy Vercel configuration: `vercel.json` rewrites all paths to the existing Railway production AIOS host, and `pyproject.toml` still identifies `src.ai_os.api:app` as the Vercel entrypoint. This preview must not be treated as OpenCompany staging. No production configuration was changed.
- [ ] The complete operating-company requirements and acceptance gates are documented in [OPENCOMPANY_OPERATING_COMPANY_SPEC.md](OPENCOMPANY_OPERATING_COMPANY_SPEC.md).

On commit `452e274d9437bc2367280ca0816c557818ac79f1`:
- **GitHub Actions full suite: 218 passed, 1 warning.**
- **OpenCompany core tests: 18 passed.**
- **OpenCompany isolated staging smoke test: passed.** Docker image built; `/health`, `/ready`, owner console and protected API checks passed; a draft work item survived container restart on the dedicated volume.
- **Vercel prebuilt validation: test step passed; output build/deployment step was skipped.** This is not a Vercel deployment.
- CI warnings include GitHub Actions Node.js action deprecation notices; no test failures were reported.
- GitHub's separate `ci/circleci: test` status reported a failure on an earlier PR head; it is pending on the latest head. Its CircleCI job page is inaccessible through the connected GitHub integration, so the earlier failure cause remains unverified.

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
- [x] GitHub Actions full test suite: 210 passed, 1 warning on commit `926f2b3881b23841c6781597063cdf7c4e850fad`.
- [x] OpenCompany core tests: 18 passed on that commit.
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


## Verification refresh — 20 Nov 2026

The current draft PR head `2841af9e77115cabf36967defbe53ef077a1fc0c` has fresh successful checks:

- GitHub Actions `tests` job passed.
- OpenCompany core tests passed.
- Isolated container smoke passed, including readiness, owner-authenticated access, and SQLite persistence across restart.
- CircleCI `ci/circleci: test` status passed.
- Vercel prebuilt validation test job passed. Its separate build/deployment job was skipped; no Vercel deployment was performed by this verification.

These checks verify code/build and isolated staging behavior only. They do not verify hosted production operation, live provider inference, or real business transactions. The PR remains draft and unmerged.
