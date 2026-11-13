# OpenCompany implementation roadmap

A capability is complete only when its implementation, acceptance tests, operational limits, and deployment behavior are verified. The standalone rebuild under `src/opencompany_app` and `src/opencompany_core` is the implementation target. The legacy `src/ai_os` application is reference-only and must not be modified as part of this rebuild.

## 1. Core platform

- [x] Standalone FastAPI application and composition root.
- [x] SQLite persistence with transactional work-item changes.
- [x] Hash-linked audit events and audit-chain verification.
- [x] Owner API-key bootstrap and revocable HttpOnly browser sessions.
- [x] CSRF checks, login throttling, security headers, and secret-free status responses.
- [x] Encrypted provider-secret storage with a dedicated encryption key.
- [x] Immutable business-unit ownership for work items, same-business dependency enforcement, inherited delegation scope, business-scoped learning notes, and per-business model-cost reporting.
- [ ] Role-based owner/operator permissions and independent security review.
- [ ] Documented secret-rotation and session-recovery procedures.

## 2. End-to-end work orchestration

- [x] Original OpenCompany organization contracts and specialist capability catalogue.
- [x] Draft provisioning for CEO, department managers, and specialist profiles.
- [x] CEO objective decomposition into validated draft department tasks.
- [x] Dependency graph validation and atomic plan persistence.
- [x] Manager-led delegation proposals with owner approval before child-task materialization.
- [x] Atomic admission of owner-approved, assigned READY work into the durable queue.
- [x] Atomic worker claims, expiring leases, bounded retries, dead-letter handling, and stale-lease recovery.
- [x] Bounded worker fleet with explicit start/stop and optional owner-configured autostart.
- [x] Specialist execution through a cost-gated model gateway; deliverables remain review-required.
- [x] Owner review, approval, revision, failure, and safe cancellation of unqueued work; state-only cancellation of queued/running work is rejected to protect active leases.
- [x] Owner-visible failed-task retry and workflow-detail inspection, backed by live queue/dependency/delegation/handoff/deliverable state.
- [x] Persisted inter-agent handoffs with identity, artifact, and audit checks.
- [x] Owner-authenticated workflow inspection endpoint for prerequisites, dependents, delegation proposals, handoffs, deliverables, queue state, and next action.
- [ ] Workflow-level artifact aggregation and specialist-specific machine-readable deliverable schemas.
- [ ] Dedicated workflow-level cancellation and resumable orchestration across parallel branches.
- [x] Durable worker-attempt records with a secret-free, owner-authenticated per-work-item execution-history endpoint (attempt number, state, timestamps, bounded error code, queue metadata and checkpoint metadata).
- [x] Owner-authenticated queue health endpoint with business-scoped counts, oldest queued age, expired leases, dead-letter count, worker fleet state, and zero-cost provider availability.
- [ ] Richer per-attempt diagnostics (provider latency/usage correlation, heartbeat events, structured failure classification and workflow-level aggregation).
- [ ] Independent multi-process/multi-host worker coordination; current fleet is designed for one persistent API container and one SQLite volume.

### Queue re-admission change

The implementation branch now allows an owner-reviewed READY task to reuse its terminal queue row after a completed review cycle or exhausted failure. Re-admission resets the attempt counter and stale lease/error fields, while refusing to overwrite queued or leased work. Regression tests have been added but remain unexecuted under the owner's instruction to defer CI/testing until 1 December 2026.

## 3. Memory, research, and learning

- [x] Role-specific operating procedures and bounded specialist prompts.
- [x] Read-only research broker with bounded operation tiers and untrusted-source handling.
- [x] Persisted agent handoffs and deliverable provenance.
- [x] Outcome evaluation against reviewable deliverables.
- [x] Owner-reviewed role-learning proposals and explicit application of approved notes.
- [x] Evidence-based improvement proposals; no automatic code or policy mutation.
- [ ] Cross-source knowledge library with granular access controls and retention rules.
- [ ] Evaluation datasets and repeatable quality/regression benchmarks.

## 4. Models and integrations

- [x] Provider-neutral model gateway with strict zero-cost request budgets.
- [x] UnoRouter live catalogue discovery and key-visible model intersection.
- [x] Free-only eligibility checks, all eligible free-model rotation, response identity checks, and non-zero-cost rejection.
- [x] Durable, secret-free model-usage ledger.
- [x] Read-only API Anything connector with bounded tier-1 operations.
- [x] Owner-verified, append-only financial event ledger with model-specific revenue classification, source-reference deduplication, order/business scope checks, and per-business/per-currency summaries.
- [ ] Provider-specific read-only commerce adapters and statement reconciliation.
- [x] GitHub code-evolution proposals restricted to isolated draft pull requests.
- [ ] WooCommerce account connection and read-only product/order sync.
- [ ] Social account connections and draft/publish workflow with owner approval.
- [ ] Email and customer-support adapters with approval-gated external messages.
- [ ] Payment-status verification adapter; no payment initiation.
- [ ] Marketplace integrations and fulfillment status sync.

## 5. Owner console and operations

- [x] Independent mobile-friendly OpenCompany owner console.
- [x] Workforce provisioning and activation controls.
- [x] CEO planning, manager delegation, task queue, worker controls, and deliverable review.
- [x] Provider catalogue/configuration and usage visibility.
- [x] Workflow details view backed by live API data.
- [x] Owner-triggered consistent SQLite backup export with integrity check.
- [ ] Automated encrypted off-host backups and retention.
- [ ] Restore rehearsal and documented recovery-point/recovery-time objectives.
- [ ] Production monitoring, alerting, and incident runbooks.
- [ ] Beginner-friendly setup and recovery guide.
- [ ] Full authenticated mobile-browser acceptance pass.

## Release and safety gates

- No paid inference, purchases, spending, publishing, customer messages, customer commitments, withdrawals, or financial actions without explicit owner approval.
- Free model eligibility is checked against the live catalogue and the owner's key; an unavailable free model must fail safely rather than fall back to a paid model.
- AI-generated code remains in isolated draft PRs. No automatic merge or production deployment.
- Keep the legacy AIOS branch unchanged and reference-only.
- Do not change production service routing, database targets, persistent volumes, or secrets as part of branch implementation without explicit owner authorization.
- CI/testing remains deferred until 1 December 2026 under the owner's existing instruction. Newly added tests must be reported as unrun until that date or until the owner changes that instruction.

## Current implementation status

The new application has a working internal CEO-to-manager-to-specialist execution path in code, including durable queueing, model-cost gates, review, handoffs, learning, and audit records. External commerce, social, email, and payment integrations are not yet connected. A successful source commit or Railway deployment alone does not prove those workflows work live; each requires an authenticated, owner-authorized acceptance test.
