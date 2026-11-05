# Roadmap

A feature is complete only when tested and its operating limits are documented. Agency Agents is the primary source for specialist role definitions and team/runbook patterns. Automaton is a secondary architecture reference only; see [AGENCY_AGENTS_ADOPTION.md](AGENCY_AGENTS_ADOPTION.md) and [AUTOMATON_REFERENCE_ASSESSMENT.md](AUTOMATON_REFERENCE_ASSESSMENT.md).

## Non-negotiable architecture requirements
- Free-first: no paid model API, paid hosting, or paid service by default.
- No silent fallback to paid providers.
- Manual free-chat work packets remain available without any API.
- Local inference is optional and must be tested on the actual host hardware.
- Owner approval before publishing, spending, purchases, customer commitments, or production changes.

## Phase 1 — Foundation (partially implemented)
- [x] FastAPI application and Python package
- [x] SQLite persistence for tasks and approvals
- [x] Human decision endpoints
- [x] Starter API tests authored
- [x] GitHub Actions test workflow authored
- [ ] Verify CI run passes
- [ ] Authentication and role-based authorization
- [ ] Structured audit log

## Phase 2 — Agency Agents-based runtime (partially implemented)
- [x] Starter agent catalog and provider-neutral registry
- [x] Exact-department specialist selection
- [x] Deterministic non-executing plan endpoint
- [x] No-API manual free-chat work packet endpoint
- [ ] Import and validate original Agency Agents Markdown profiles and runbooks with license attribution
- [ ] Provider-neutral inference interface with strict free-only mode
- [ ] Task planner with dependency graph, agent assignment, handoffs, and execution records
- [ ] Timeouts, retries, idempotency, and failure handling
- [ ] Background worker and durable scheduler

## Phase 3 — Memory, learning, and evaluation
- [ ] Source-attributed company knowledge store
- [ ] Retrieval with company/user access boundaries
- [ ] Evaluation datasets and regression checks for agent outputs
- [ ] Daily research/learning proposals with evidence and source links
- [ ] Human approval for changes to prompts, policies, and production behavior

## Phase 4 — Business operations
- [ ] WooCommerce integration
- [ ] Social platform content planning and draft generation
- [ ] Human approval before any external publishing
- [ ] Customer support inbox and response drafts
- [ ] Payment-status verification only; no autonomous money movement

## Phase 5 — Operations and release
- [ ] Dashboard and role-based access
- [ ] Deployment profiles, backups, monitoring, and alerting
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide and operator handbook

## Reference decisions
- Agency Agents: primary source of specialist roles and workflow patterns.
- Automaton: selective patterns for ReAct loops, durable scheduling, task graphs, local workers, model routing, memory, policy enforcement, and auditability.
- Exclude Conway billing/sandbox dependencies, wallets/USDC, x402 payments, autonomous spending, self-replication, unrestricted shell access, and automatic production self-modification.

## Safety boundaries

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes. Prompt instructions are not security controls: enforce permissions in the runtime and integration layer.
