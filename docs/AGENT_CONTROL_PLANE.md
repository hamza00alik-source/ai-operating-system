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

### CP-1 — Registry data model and read APIs — implemented
- Additive SQLite schema for logical agents, endpoint metadata, and agent relationships.
- Seed and synchronize logical agent records from the pinned Agency Agents profile catalogue; preserve owner enable/disable choices across restarts.
- Expose owner-authenticated list, detail, department/enabled filters, enable/disable, and endpoint-registration APIs.
- Register internal, MCP, A2A, and OpenAI-compatible endpoint metadata; network endpoints remain disabled and are not contacted.
- Store profile capabilities as descriptive metadata only; they are not executable permissions.
- Protect the CEO accountability root from being disabled.
- Validate HTTPS for remote endpoints, permit HTTP only for localhost, reject URL-embedded credentials/query strings, and accept only secret-manager/environment references rather than raw credentials.
- Add automated tests for seeding, relationships, filters, enable/disable, owner authentication, endpoint validation, and CEO protection.
- GitHub Actions passed the full suite: 235 tests passed on the CP-1 branch.

### CP-2 — Runtime identity and heartbeat — implemented
- Add a persistent runtime-instance registry for generic worker processes and logical-agent runtime identities.
- Owner-authenticated registration returns a high-entropy runtime credential once; only its SHA-256 hash is stored.
- Runtime credentials expire after 30 days and can be rotated by the owner; rotation immediately invalidates the previous credential.
- Owner revocation immediately blocks further heartbeats. Disabling a logical agent also revokes every runtime identity assigned to it.
- A separate runtime-authenticated heartbeat endpoint records status, current job ID, and last-seen time. The endpoint bypasses the owner-token middleware only because it verifies the runtime-specific credential itself.
- Runtime health is derived from heartbeat evidence: never-seen runtimes are offline; heartbeats older than 60 seconds are stale; revoked runtimes are revoked.
- The worker service supports optional remote heartbeat reporting using `AI_OS_CONTROL_PLANE_URL`, `AI_OS_RUNTIME_ID`, and `AI_OS_RUNTIME_TOKEN`. It refreshes heartbeats during long-running jobs, not only between jobs.
- The owner token and runtime credentials are separate. Runtime credentials authorize heartbeat reporting only; they do not grant queue, model, MCP, A2A, or external-action permissions.
- GitHub Actions passed the full suite: 250 tests.

Operational setup:
1. Register a worker through the owner-authenticated `POST /control-plane/runtimes` endpoint with `runtime_kind: "worker"`.
2. Copy the returned token once into the worker host's secret environment as `AI_OS_RUNTIME_TOKEN`; set `AI_OS_RUNTIME_ID` and `AI_OS_CONTROL_PLANE_URL` alongside it.
3. Restart the worker service and confirm its authenticated heartbeat in `GET /control-plane/runtimes`.
4. Rotate the token before its 30-day expiry; revoke the runtime if the host is retired or compromised.

Limitations: this milestone registers and monitors runtime identities; it does not yet provide remote job claiming or a distributed queue transport. The worker still needs access to the configured durable queue/database to execute jobs. Registering an agent runtime does not by itself launch an independent AI process.

### CP-3 — Broker and policy enforcement — in progress

Implemented baseline enforcement:
- Add effective-agent resolution that requires both the pinned profile registry and the persistent Control Plane enabled state to permit an agent.
- Apply that check when building work packets, issuing/verifying signed agent identities, validating new company-run assignments, evaluating CEO governance actions, accepting logical-agent runtime heartbeats, and starting already-queued specialist inference.
- Route deterministic CEO department selection, CEO objective planning, manager delegation, and department workload availability through effective-agent policy.
- Keep bulk department filtering to one Control Plane query rather than one database connection per profile.
- Expose effective enabled/disabled state in the existing owner `/agents` API so the dashboard does not present stale registry-only status.
- Add regression coverage proving a Control Plane-disabled agent cannot receive a packet, identity, or new company-run assignment.

Implemented broker and capability controls:
- Add an inspectable CEO/manager route evaluator at owner-authenticated `POST /control-plane/broker/evaluate`. CEO routes may target any enabled logical agent; non-CEO delegation is limited to the configured manager of the target agent's department and requires a seeded, department-scoped `task.delegate` grant. Self-delegation and cross-department manager routes are denied.
- Enforce the same broker route policy while department managers build specialist plans; only policy-approved specialists are eligible.
- Add owner-managed explicit grants at `GET/POST /control-plane/capabilities`, revocation at `DELETE /control-plane/capabilities/{grant_id}`, and policy preview at `POST /control-plane/capabilities/evaluate`.
- Capability checks fail closed for unknown capabilities, disabled agents, and missing grants. The supported initial capability vocabulary is `task.delegate`, `tool.research.read`, `tool.knowledge.read`, `tool.knowledge.write`, `tool.store.read`, and `tool.store.draft`.
- Seed each department manager with only the `task.delegate` capability for the department named in the company charter. This does not grant tool access.
- Add a trusted in-process agent-tool adapter registry. Each tool adapter is registered by application code with one supported `tool.*` capability; execution requires an explicit matching Control Plane grant, JSON-object parameters and results capped at 64 KiB, and writes start/deny/success/failure events to the hash-chained audit log.
- Register bounded read-only tools at application startup: `research.release_feeds` (fixed public GitHub release feeds, no paid search provider), `knowledge.search` (owner-accepted company knowledge only), `store.products.read`, and `store.orders.read` (minimized order/payment status only).
- Add a bounded specialist model/tool loop: a specialist may request at most three registered tools per step. Tool outputs are passed back as untrusted data. Unknown tools, disabled agents, missing grants, invalid JSON parameters, and oversized parameters are rejected.
- Keep specialist tool calling separately disabled by default with `AI_OS_AGENT_TOOL_CALLS_ENABLED=false`. Enabling the model adapter does not automatically enable tool calls. Each tool still requires a matching owner-managed capability grant.
- Preserve the separate exact-scope owner approval gateway for external actions. Agent-tool adapters are not exposed through remote endpoint registration and do not enable MCP/A2A networking.
- Extend the action gateway readiness view to distinguish owner-approved external actions from capability-gated internal agent tools and show whether specialist tool calls are enabled.
- Add an owner-dashboard panel showing Control Plane agent/runtime counts, tool-call readiness, registered internal adapters, explicit capability grants, and recent broker/tool audit events. Owners can grant and revoke capabilities directly from the dashboard; each change calls the owner-authenticated API and is audited.

Operator activation:
1. Keep `AI_OS_AGENT_TOOL_CALLS_ENABLED=false` unless the owner has reviewed the model provider's cost/usage implications and the enabled tools.
2. Grant only the required capability to selected agents through owner-authenticated `POST /control-plane/capabilities`; review current grants with `GET /control-plane/capabilities`.
3. Confirm registered adapters and the tool-call switch through `GET /actions/gateway/status`.
4. WooCommerce tools remain unavailable until the existing read-only store credentials are configured; they expose bounded catalog and minimized order status only. No publishing, product/order writes, refunds, or customer messages are included.

Validation:
- GitHub Actions passed the full suite: 270 tests.

Remaining CP-3 work:
- Continue adversarial testing of task-level budgets, transient provider failures, and worker recovery under real deployment conditions.

Profile capability metadata remains descriptive and is never treated as an executable grant. Runtime credentials still authorize heartbeat reporting only. Remote MCP/A2A endpoints remain disabled and unconnected until CP-4.

### CP-4 — MCP, then A2A

MCP is the next integration boundary. It must not weaken the CP-3 in-process capability gateway.

Required implementation sequence:
1. Add an explicit owner enable/disable lifecycle for each registered MCP endpoint. Registration remains metadata-only and disabled by default.
2. Resolve only `env:NAME` credential references from the worker process environment; never return resolved credentials from an API or log them. Reject unresolved `secret://` references until a real secret-manager adapter exists.
3. Require HTTPS for remote MCP endpoints; permit HTTP only for loopback development. Resolve and reject non-public destination addresses, prohibit redirects, cap request/response sizes and timeouts, and avoid forwarding credentials across origins.
4. Implement the supported MCP Streamable HTTP transport with protocol-version negotiation, initialization/session handling, strict JSON-RPC validation, and bounded `tools/list` / `tools/call` requests. Reject unsupported transports and malformed or unexpected response content types.
5. Treat remote tool descriptions and all remote results as untrusted data. Never let a remote server change agent permissions, approval policy, endpoint metadata, or owner settings.
6. Map each discovered remote tool to a locally owner-approved capability grant. An endpoint being enabled or a tool being discovered must not grant an agent permission to call it.
7. Route remote calls through the same audited agent-tool gateway, enforce per-agent and per-step budgets, and keep all external side effects behind the existing exact-scope owner approval gateway.
8. Test DNS/IP restrictions, redirects, TLS policy, credential handling, oversized payloads, malformed JSON-RPC, session expiry, timeout/retry behavior, capability revocation, prompt injection in tool results, and endpoint disable during an active call.

Implemented CP-4 preparation: owner-authenticated `PATCH /control-plane/endpoints/{endpoint_id}` can enable or disable registered MCP endpoint metadata. Activation is limited to MCP (A2A/OpenAI-compatible endpoint execution remains disabled), and any credential reference must resolve to an existing `env:NAME` variable. Unresolved `secret://` references fail closed. The API response explicitly states that activation does not connect to the endpoint. This lifecycle is not yet an MCP client.

No MCP endpoint is currently connected or executed. The CP-1 endpoint registry is metadata-only; the above is an acceptance plan, not a claim of MCP support.

A2A follows only after MCP identity, endpoint lifecycle, and capability mapping are proven. A2A must use signed identity, replay protection, scoped delegation, bounded task state, and the same owner-approval boundary; it must not create a second permission system.

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
