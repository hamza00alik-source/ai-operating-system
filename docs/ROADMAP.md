# Roadmap

A feature is complete only when tested and its operating limits are documented. Agency Agents is the primary source for specialist role definitions and team/runbook patterns. Automaton is a secondary architecture reference only; see [AGENCY_AGENTS_ADOPTION.md](AGENCY_AGENTS_ADOPTION.md) and [AUTOMATON_REFERENCE_ASSESSMENT.md](AUTOMATON_REFERENCE_ASSESSMENT.md). The ten pinned public reference repositories are reviewed weekly; see [REFERENCE_REVIEW_2026-11-06.md](REFERENCE_REVIEW_2026-11-06.md).

## Non-negotiable architecture requirements
- Free-first: no paid model API, paid hosting, or paid service by default.
- No silent fallback to paid providers or anonymous hosted inference.
- Manual free-chat work packets remain available without any API.
- Local inference is optional and must be tested on the actual host hardware.
- The CEO agent is accountable for every company action; department agents work under its direction.
- Only the CEO agent may request owner approval for publishing, spending, purchases, customer commitments, refunds, or production/security changes.

## Phase 1 — Foundation (partially implemented)
- [x] FastAPI application and Python package
- [x] SQLite persistence for tasks, approvals, and durable jobs
- [x] Human decision endpoints
- [x] Starter API tests authored
- [x] GitHub Actions test workflow authored
- [x] Single-owner API token gate with production fail-closed behavior
- [x] Python host entry point and Enzonic deployment preparation guide (deployment itself remains pending)
- [x] Append-only SQLite audit trail with SHA-256 chain verification
- [x] Request IDs and request metadata logging without credentials or request bodies
- [x] CEO accountability policy, internal-action allowlist, sensitive-action escalation, and fail-closed unknown-action handling
- [x] Approval inbox restricted to the owner-approval action allowlist
- [ ] Verify CI run for latest security/audit commit
- [ ] Secret rotation, rate limiting, and recovery procedures
- [x] Signed CEO-only approval-request ingress, owner-authenticated exact-scope decisions, expiry, audit events, and owner dashboard inbox
- [x] Internal action gateway with adapter registry, exact approval consumption, disabled-by-default switch, and audited outcomes
- [ ] Production adapter sandboxing, reconciliation, and external-action integration tests
- [ ] Role-based authorization for specialist agents and worker operations
- [x] SQLite online backup helper with integrity/schema/audit-chain verification and automated tests
- [x] Verified atomic SQLite restore helper with explicit overwrite acknowledgement and tests
- [ ] Off-host encrypted backup policy, retention automation, and signed external audit checkpoints

## Phase 2 — Agency Agents-based runtime (partially implemented)
- [x] CEO Agent designated as company leader and single owner-approval gateway (policy layer only)
- [x] Complete pinned Agency Agents library: 283 specialist profiles across 18 divisions
- [x] Dynamic frontmatter registry with all imported specialists enabled
- [x] Full profile API and specialist work packets with CEO reporting rules
- [x] Starter CEO catalogue and provider-neutral registry
- [x] Exact-department specialist selection
- [x] Deterministic non-executing plan endpoint
- [x] No-API manual free-chat work packet endpoint
- [x] Persistent queue with idempotent enqueue, atomic claim, bounded retries, stale-lease recovery, and one local handler
- [x] Process-level worker recovery loop with bounded exponential backoff (host/process supervision still required)
- [x] Pin original Agency Agents Markdown profiles as a read-only MIT-licensed Git submodule; retain upstream LICENSE and runbooks
- [x] Add automated source-pin drift checks and frontmatter validation in CI (18 divisions, 283 profiles, runbook references, and Git submodule pin; GitHub Actions passing)
- [x] Provider-neutral, opt-in OpenAI-compatible inference adapter (local endpoints permitted; no provider enabled by default)
- [x] Task planner with dependency graph, agent assignment, handoffs, and execution records
- [x] Durable scheduler and persistent worker process for bounded specialist execution
- [x] Blocked dependency propagation and terminal run-state reconciliation
- [x] Specialist step finalization when durable retries are exhausted
- [x] Signed, run-bound specialist report capability and authenticated report acceptance
- [ ] Broader role-based authorization for future worker tools and integrations

## Phase 3 — Memory, learning, and evaluation
- [x] Source-attributed company knowledge candidates with owner review and audit trail
- [x] Bounded keyword retrieval of owner-accepted knowledge with source context
- [x] Agent-proposed knowledge candidates with source-context URL gate and owner review
- [ ] Semantic retrieval with embeddings (still lexical and provider-free)
- [x] Exact knowledge deduplication and publication-date freshness tie-breaker (heuristic only)
- [x] Explicit company vs owner-only knowledge scope; agent retrieval excludes owner-only records (single-owner deployment; full user/role RBAC remains pending)
- [x] Deterministic specialist-report evaluation rubric and CI regression fixtures (structure/safety signals only)
- [x] Persisted evaluation history and sample-gated quality trend API/dashboard
- [x] Owner-reviewed training-example candidates with rights/privacy attestations and one-time review
- [x] Private accepted-only versioned JSONL dataset exports with SHA-256 manifests
- [ ] Task-specific evidence and factuality evaluation datasets
- [x] Idempotent daily internal CEO review-plan generator and scheduler command (persisted company data only)\n- [ ] Daily external research/learning proposals with verified search sources, evidence links, and publication dates
- [x] Rule-based CEO improvement proposals linked to repeated failed evaluation checks; owner review required before testing
- [x] Isolated static text/policy screen for owner-approved candidate instructions with persisted test results (not a model-behavior test)
- [x] Immutable per-agent instruction addendum versions bound to upstream profile hashes
- [x] Owner-authenticated activation only after a passing static screen of the exact candidate text
- [x] Audited rollback to the prior immutable instruction version
- [x] Optional local-only baseline-vs-candidate model behavior regression harness with fixed fixtures, persisted results, and owner-token API (limited regression signal)
- [ ] Broader task-specific quality, factuality, and domain regression datasets
- [x] Human approval before activating agent instruction addenda
- [ ] Owner-approved changes to core security policies and production behavior

## Phase 4 — Business operations
- [x] Read-only WooCommerce product catalog and minimized order-status connector
- [x] Owner-protected WooCommerce status, product, and minimized order-status API endpoints
- [x] Owner dashboard Store & Website overview for connection status, bounded product inventory, and coarse recent order statuses
- [x] Read-only WordPress posts/pages inventory connector with HTTPS, bounded pagination, minimized metadata, and GET-only tests
- [x] Owner-approved WordPress new-page draft creation through exact-scope, one-time approval and explicit owner execution (publishing and updates remain disabled)
- [x] Owner-approved WooCommerce new-product draft creation through exact-scope, one-time approval and explicit owner execution (publishing and all order writes remain disabled)
- [ ] Other WooCommerce write operations, order fulfillment, and reconciliation
- [ ] Social platform content planning and draft generation
- [ ] Human approval before any external publishing
- [ ] Customer support inbox and response drafts
- [x] Read-only WooCommerce payment confirmation signal from date_paid; no autonomous money movement or independent settlement reconciliation

## Phase 5 — Operations and release
- [x] Owner dashboard for agent, run, queue, approval, audit, model, evaluation trends, and improvement proposal review
- [ ] Broader role-based access and operational dashboard hardening
- [ ] Deployment profiles, backups, monitoring, and alerting
- [ ] Security review and end-to-end tests
- [x] Beginner-friendly Google Cloud Shell smoke-test setup guide (model and external actions remain disabled by default)
- [x] Operator playbook covering daily coordination limits, model execution, worker supervision, WooCommerce read-only setup, backup/restore, and release gates
- [ ] Production deployment guide with a verified persistent host, TLS, monitoring, and rollback

See [OPERATIONS_PLAYBOOK.md](OPERATIONS_PLAYBOOK.md), [CONTINUOUS_LEARNING.md](CONTINUOUS_LEARNING.md), [INSTRUCTION_VERSIONING.md](INSTRUCTION_VERSIONING.md), [BEHAVIOR_TESTING.md](BEHAVIOR_TESTING.md),  [OWN_MODEL_STRATEGY.md](OWN_MODEL_STRATEGY.md) for the company-owned model plan, and [ACTION_GATEWAY.md](ACTION_GATEWAY.md) for the action execution boundary.

## Phase 6 — Agent control plane (CP-1 and CP-2 implemented; CP-3 in progress)
- [x] Define a zero-cost, provider-neutral control-plane architecture inspired by Agent Fabric capabilities
- [x] Document the distinction between profile catalog entries, logical agents, and live runtime instances
- [x] CP-1: SQLite registry for logical agents, profile capability metadata, endpoint metadata, and agent relationships; owner APIs, disabled-by-default endpoints, CEO-root protection, and automated tests (235 tests passing)
- [x] CP-2: runtime-instance records, one-time hashed credentials with 30-day expiry, owner rotation/revocation, authenticated heartbeats, stale detection, and worker keepalives (250 tests passing)
- [x] CP-3 baseline: effective-agent enforcement across work packets, identities, company-run assignment, CEO/manager routing, department workload, and dashboard status (full CI passing)
- [x] CP-3 broker: inspectable CEO/manager route evaluation, department-scoped manager delegation, self/cross-department route denial, and policy enforcement in manager workflows
- [x] CP-3 capabilities: owner-managed explicit capability grants/revocation, deny-by-default checks, and trusted in-process tool adapter execution with audit events
- [x] CP-3 built-ins: bounded free release-feed research, owner-accepted knowledge search, and read-only WooCommerce catalog/order-status tools
- [x] CP-3 specialist tool loop: opt-in model-requested tool calls, maximum three calls per step, untrusted tool-result handling, and disabled-by-default switch
- [x] CP-3 observability: owner dashboard shows Control Plane health, capability grants, tool readiness, and recent broker/tool audit events
- [ ] CP-3 remaining: adversarial/task-budget hardening and provider-failure recovery
- [ ] CP-4: secure MCP integration, followed by A2A interoperability after identity and policy controls
- [ ] CP-5: live health, job telemetry, policy traces, and agent-network visualization
- [ ] CP-6: production deployment hardening, monitoring, backup/restore, and rollback verification

See [AGENT_CONTROL_PLANE.md](AGENT_CONTROL_PLANE.md) for architecture, trust boundaries, sequence, and acceptance criteria. CP-1 and CP-2 are implemented on this branch. CP-3 baseline, broker routing, explicit capability grants, trusted tool dispatch, four read-only built-ins, and the opt-in bounded specialist tool loop are implemented and tested (261 tests passed at the last validated code commit). Dashboard policy traces and further operational hardening remain in progress. CP-4 through CP-6 remain planned.

## Reference decisions
- Agency Agents: primary source of specialist roles and workflow patterns.
- Automaton: selective patterns for ReAct loops, durable scheduling, task graphs, local workers, model routing, memory, policy enforcement, and auditability.
- The ten other public repositories: reviewed weekly; adopt only compatible, license-aware patterns. Current review is in [REFERENCE_REVIEW_2026-11-06.md](REFERENCE_REVIEW_2026-11-06.md).
- Exclude Conway billing/sandbox dependencies, wallets/USDC, x402 payments, autonomous spending, self-replication, unrestricted shell access, and automatic production self-modification.

## Safety boundaries

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes. Prompt instructions are not security controls: enforce permissions in the runtime and integration layer. The current token gate is not full RBAC; keep the service local-only until remaining hardening work is complete.
