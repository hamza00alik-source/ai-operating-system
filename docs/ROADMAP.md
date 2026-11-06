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
- [x] Append-only SQLite audit trail with SHA-256 chain verification
- [x] Request IDs and request metadata logging without credentials or request bodies
- [x] CEO accountability policy, internal-action allowlist, sensitive-action escalation, and fail-closed unknown-action handling
- [x] Approval inbox restricted to the owner-approval action allowlist
- [ ] Verify CI run for latest security/audit commit
- [ ] Secret rotation, rate limiting, and recovery procedures
- [ ] Authenticated agent identities and runtime-enforced CEO-only approval requests (policy preview exists; this is not yet enforced at real tool boundaries)
- [ ] Role-based authorization for specialist agents and worker operations
- [x] SQLite online backup helper with integrity/schema/audit-chain verification and automated tests
- [ ] Restore workflow, off-host backup policy, retention, and signed audit checkpoints

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
- [x] Pin original Agency Agents Markdown profiles as a read-only MIT-licensed Git submodule; retain upstream LICENSE and runbooks
- [ ] Add automated source-pin drift checks and frontmatter validation in CI
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
- [ ] Semantic retrieval, deduplication, and freshness scoring
- [ ] Retrieval with company/user access boundaries
- [x] Deterministic specialist-report evaluation rubric and CI regression fixtures (structure/safety signals only)\n- [ ] Persisted evaluation history and quality trend tracking\n- [ ] Task-specific evidence and factuality evaluation datasets
- [ ] Daily research/learning proposals with evidence and source links\n- [x] Rule-based CEO improvement proposals linked to repeated failed evaluation checks; owner review required before testing\n- [ ] Isolated candidate-instruction regression harness and owner-approved adoption workflow
- [ ] Human approval for changes to prompts, policies, and production behavior

## Phase 4 — Business operations
- [ ] WooCommerce integration
- [ ] Social platform content planning and draft generation
- [ ] Human approval before any external publishing
- [ ] Customer support inbox and response drafts
- [ ] Payment-status verification only; no autonomous money movement

## Phase 5 — Operations and release
- [x] Owner dashboard for agent, run, queue, approval, audit, model, evaluation trends, and improvement proposal review
- [ ] Broader role-based access and operational dashboard hardening
- [ ] Deployment profiles, backups, monitoring, and alerting
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide and operator handbook

See [CONTINUOUS_LEARNING.md](CONTINUOUS_LEARNING.md) for the current learning/evaluation implementation and its limits.\n\n## Reference decisions
- Agency Agents: primary source of specialist roles and workflow patterns.
- Automaton: selective patterns for ReAct loops, durable scheduling, task graphs, local workers, model routing, memory, policy enforcement, and auditability.
- The ten other public repositories: reviewed weekly; adopt only compatible, license-aware patterns. Current review is in [REFERENCE_REVIEW_2026-11-06.md](REFERENCE_REVIEW_2026-11-06.md).
- Exclude Conway billing/sandbox dependencies, wallets/USDC, x402 payments, autonomous spending, self-replication, unrestricted shell access, and automatic production self-modification.

## Safety boundaries

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes. Prompt instructions are not security controls: enforce permissions in the runtime and integration layer. The current token gate is not full RBAC; keep the service local-only until remaining hardening work is complete.
