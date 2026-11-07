# Agent Control Plane — MuleSoft Agent Fabric-inspired design

## Decision

Build the control-plane capabilities inside this AI Operating System. Do not add MuleSoft as a runtime dependency. MuleSoft Agent Fabric is a useful enterprise reference for agent discovery, orchestration, governance, and observability, but its commercial platform is outside this project's zero-budget requirement.

This document is an implementation specification, not a claim that these capabilities are already complete.

## Current verified baseline

On `feat/agency-agents-foundation`, the repository already contains:

- A pinned Agency Agents library with 283 specialist profiles across 18 divisions.
- A provider-neutral specialist registry and profile API.
- CEO-led plans, dependency-aware company runs, durable jobs, and a persistent worker service.
- Optional model-backed specialist execution, disabled unless an owner configures a compatible endpoint.
- Owner dashboard, audit chain, exact-scope approval requests, evaluation history, and improvement review.
- A read-only WordPress/WooCommerce connection layer and separately gated draft creation paths.

Important distinction: a profile in the registry is an available role definition, not a running process. The current worker service executes queued work; it does not run 283 independent agents continuously. External actions remain gated and incomplete.

## Goals

1. Discover and describe every agent, worker, model endpoint, MCP server, and approved tool in one owner-visible inventory.
2. Route work deterministically through the CEO and department managers, with model reasoning used only where configured.
3. Track actual runtime health separately from profile availability and workflow progress.
4. Enforce permissions in code, not in prompts.
5. Record traceable task, agent, tool, and approval events without storing secrets or unnecessary customer data.
6. Remain provider-neutral and free-first; no paid fallback, subscription, or usage-based service may be enabled silently.

## Target architecture

```text
Owner dashboard
      |
      v
Control-plane API
  |       |        |          |
Registry Broker Governance Observability
  |       |        |          |
  +-------+--------+----------+
                  |
             CEO Agent
                  |
       Department managers
                  |
      Specialist execution queue
                  |
       Worker process / adapters
          |        |         |
        Model     MCP      Internal APIs
       endpoint  servers   (allowlisted)
```

The CEO remains accountable for company-level actions and is the only agent allowed to request owner approval for sensitive actions. Department managers may coordinate specialist work but cannot approve actions or bypass the CEO/owner boundary.

## Control-plane components

### 1. Agent and service registry

A future registry record should distinguish these concepts:

- `profile`: static role instructions from the pinned Agency Agents library.
- `logical_agent`: an assignable identity that uses a profile and has a stable ID.
- `runtime_instance`: a worker or remote agent process that has actually checked in.
- `capability`: a named, versioned operation an agent is permitted to request.
- `endpoint`: a configured model, A2A agent, or MCP server connection.

Minimum metadata: stable ID, display name, profile ID, department, source, capabilities, protocol, endpoint reference (never credentials), enabled state, owner, created/updated timestamps, and policy version.

Do not infer that an agent is online because its profile exists. Runtime status must come from a recent authenticated heartbeat or a successful health probe. Unknown/stale status must be displayed as unknown, not healthy.

### 2. Broker and task routing

The CEO remains the top-level broker. Routing should be deterministic first:

1. Validate the objective and classify its risk.
2. Select a department using explicit routing rules.
3. Select a specialist by capability and department.
4. Verify dependencies and permissions.
5. Enqueue an idempotent job.
6. Dispatch only to a healthy, enabled worker/runtime.
7. Collect a signed, run-bound report.
8. Let the CEO review outcomes and decide whether another step is needed.

LLM-based routing may propose a route, but the policy engine validates it before execution. Every routing decision records the selected agent, reason, policy version, and fallback outcome.

### 3. Protocol interoperability

Implement in stages:

- Internal typed Python interface first; no network protocol required for local agents.
- MCP client/server support only for explicitly allowlisted tools, with schemas, timeouts, output limits, and per-tool permissions.
- A2A discovery and task exchange only after identity, authentication, authorization, replay protection, timeouts, and audit behavior are tested.

Do not expose an unauthenticated public MCP or A2A endpoint. Do not let remote agents inherit owner privileges.

### 4. Governance and approvals

All actions pass through a policy evaluator before dispatch. Default-deny unknown capabilities.

Permission tiers:

- Read-only internal analysis.
- Internal state mutation (task notes, plans, knowledge candidates).
- External read access (specific store/site APIs).
- External draft creation (exact owner-approved scope).
- Sensitive actions: publishing, purchases, spending, refunds, customer commitments, messaging, deployment, security/policy changes.

Sensitive actions require the existing signed CEO request and a separate owner decision. Approval must be exact-scope, expiring, one-time, audited, and bound to the action parameters. Approval authorizes only the stated action; it must not silently authorize related actions.

### 5. Observability and dashboard

Show separate indicators for:

- Profile available / disabled.
- Runtime online / stale / offline / unknown.
- Current job and queue age.
- Last heartbeat and last completed task.
- Success/failure/retry counts.
- Recent error category (redacted).
- Model provider and model identifier (never API keys).
- Tool calls and policy decisions.
- Token/cost usage only when the provider actually returns reliable usage metadata.

A visual network graph should show agents, brokers, workers, MCP servers, model endpoints, and directed relationships. The graph is a view of recorded configuration and telemetry, not proof that a link is healthy.

### 6. Reliability

Use the existing durable queue as the source of truth. Add authenticated worker leases/heartbeats, bounded retries, stale-lease recovery, idempotency, dead-letter visibility, and explicit cancellation. A worker restart must not duplicate a completed external action. Before any production adapter is enabled, add reconciliation and integration tests.

## Implementation sequence

### CP-0 — Specification and baseline (this change)
- Record architecture, trust boundaries, current limitations, and staged implementation.
- Keep the existing Agency Agents branch intact.

### CP-1 — Registry data model and read APIs
- Add SQLite tables for runtime instances, capabilities, endpoints (credential references only), and agent-to-service relationships.
- Add owner-authenticated registration, enable/disable, list, detail, and health-status APIs.
- Seed logical agents from the existing profile registry without pretending they are running.
- Add migration, validation, and tests.

### CP-2 — Runtime identity and heartbeat
- Give each worker/runtime a revocable identity with least privilege.
- Add signed heartbeat and job-lease renewal, expiry, replay protection, and last-seen state.
- Keep the owner token separate from worker credentials.

### CP-3 — Broker and policy enforcement
- Make CEO routing decisions inspectable and policy-validated.
- Add capability allowlists, department scopes, and deny-by-default tool dispatch.
- Preserve existing exact-scope owner approvals.

### CP-4 — MCP, then A2A
- Implement a local MCP adapter registry and safe client for allowlisted tools.
- Add protocol conformance and security tests before any remote endpoint is enabled.
- Add A2A only after runtime identity and policy enforcement are complete.

### CP-5 — Observability and visual topology
- Add runtime heartbeats, job metrics, error summaries, policy traces, and graph relationships to the owner dashboard.
- Clearly label stale/unknown states and distinguish profiles from live processes.

### CP-6 — Deployment and release hardening
- Verify persistent storage, HTTPS, secret rotation, rate limits, backups, restore, monitoring, and rollback on the actual selected host.
- Keep production deployment and external write adapters disabled until the owner approves a tested release.

## Zero-budget and safety rules

- No MuleSoft dependency.
- No paid API, hosting, connector, or SaaS service by default.
- No automatic paid-provider fallback.
- No secrets in registry metadata, logs, Git, dashboard HTML, or agent prompts.
- No autonomous spending, purchases, publishing, customer commitments, refunds, or unattended production changes.
- No claim of 24/7 operation until the selected host, persistent storage, worker supervision, and recovery have been tested.
- Free tiers and trials are not assumed to be permanent or production-reliable; verify their limits before deployment.

## Acceptance criteria

A control-plane milestone is complete only when:

- Migrations are safe and repeatable.
- Every new endpoint has owner/worker authentication tests.
- Unknown capabilities and unregistered endpoints fail closed.
- Runtime health is derived from authenticated evidence and expires correctly.
- Retries, duplicate requests, stale leases, revocation, and worker restarts are tested.
- Audit events contain enough context to reconstruct decisions but no credentials or sensitive payloads.
- Dashboard labels distinguish catalog entries, logical agents, and live runtime instances.
- Existing company-run, approval, backup, and store-integration tests continue to pass.
