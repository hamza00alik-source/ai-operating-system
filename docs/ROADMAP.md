# Roadmap

A feature is complete only when tested and its operating limits are documented. Agency Agents is the primary source for specialist role definitions and team/runbook patterns; see [AGENCY_AGENTS_ADOPTION.md](AGENCY_AGENTS_ADOPTION.md).

## Phase 1 — Foundation (partially implemented)
- [x] FastAPI application and Python package
- [x] SQLite persistence for tasks and approvals
- [x] Human decision endpoints
- [x] Starter API tests authored
- [x] GitHub Actions test workflow authored
- [ ] Verify CI run passes
- [ ] Authentication and role-based authorization
- [ ] Structured audit log

## Phase 2 — Agency Agents-based runtime
- [ ] Define validated agent profile schema and Markdown importer
- [ ] Build agent registry with source/license attribution
- [ ] Select and adapt initial CEO/orchestrator, project manager, researcher, product, engineer, marketer, QA, and support roles
- [ ] Provider-neutral LLM adapter interface
- [ ] Task planner, agent assignment, handoffs, dependencies, and execution records
- [ ] Timeouts, retries, idempotency, and failure handling
- [ ] Background worker and scheduler

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

## Safety boundaries

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes. Prompt instructions are not security controls: enforce permissions in the runtime and integration layer.
