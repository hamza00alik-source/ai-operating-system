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
- [ ] Repair and test worker package (current worker service imports modules absent from the default-branch tree)
- [ ] Task dependencies, assignment, leases, and cancellation
- [ ] Agent interface, registry, typed inputs/outputs, and department routing
- [ ] Retry policy, timeouts, concurrency limits, execution logs, and idempotency
- [x] Provider-neutral OpenAI-compatible model adapter, disabled by default, with bounded request settings\n- [x] Protected model status/test endpoints and provider discovery metadata\n- [ ] Verify one real free-tier or documented keyless model call with owner-approved provider configuration\n- [ ] Add provider-specific adapters and zero-cost-first routing with hard cost ceilings
- [ ] Central approval service enforced for every protected action
- [ ] Optional LangGraph adapter after core queue/approval prerequisites pass (see [LangGraph decision](LANGGRAPH_ARCHITECTURE_DECISION.md))
- [ ] Background worker and scheduler with restart/recovery tests

## Phase 3 — Memory and learning
- [ ] Source-attributed company knowledge
- [ ] Retrieval and access controls
- [ ] Evaluation datasets and regression checks
- [ ] Improvement proposals requiring human approval

## Phase 4 — Integrations
- [ ] MCP server registry with allowlists, scoped credentials, timeouts, and audit logs
- [ ] Provider and tool health checks; no automatic paid fallback
- [ ] WooCommerce
- [ ] Social adapters with mandatory approval
- [ ] Email and support adapters
- [ ] Payment-status verification only

## Phase 5 — Operations
- [ ] Dashboard, deployment profiles, backups
- [ ] Security review and end-to-end tests
- [ ] Beginner-friendly setup guide

No autonomous spending, purchases, publishing, customer commitments, or unattended production code changes in the early releases.

## External AI tool evaluation (2026-11-08)
- [x] Evaluate free LLM API directory, Orca, OpenHands, Dify, and LibreChat references
- [x] Record selective adoption and security/cost boundaries in [video tool evaluation](VIDEO_TOOL_EVALUATION.md)
- [ ] Build curated, disabled-by-default provider catalogue and model adapter
- [ ] Verify one real free-tier or documented keyless model call
- [ ] Pilot OpenHands only in a separate isolated developer sandbox
- [ ] Consider LibreChat as an optional UI after AIOS APIs stabilize
- [ ] Do not adopt Dify or Orca as required AIOS runtime dependencies

- [x] Repair missing worker runtime imports with task executor and lease scheduler
- [x] Add SQLite task result, retry, worker lease, and recovery fields using additive migrations
- [x] Add worker process supervisor with bounded backoff and graceful SIGINT/SIGTERM shutdown
- [x] Add tests for task execution, result persistence, transient retry, expired lease recovery, and retry exhaustion
- [ ] Validate worker against a real approved model endpoint (requires owner provider configuration)
- [ ] Add agent registry and multi-agent handoff on top of the durable task queue
- [ ] Add MCP server registry, tool allowlist, and approval-gated invocation
