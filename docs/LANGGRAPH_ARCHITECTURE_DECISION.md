# LangGraph Architecture Decision

**Status:** Accepted as an architectural reference; runtime integration deferred  
**Decision owner:** OpenCompany AI CEO  
**Constraint:** Preserve the existing AIOS, zero spend, no production credential changes, no external actions.

## Executive decision

Use LangGraph as the preferred candidate for explicit, stateful workflow orchestration when OpenCompany reaches the orchestration implementation stage. Do not replace the current AIOS, do not install LangGraph as an untested dependency yet, and do not move company records or approval authority into a separate agent platform.

The screenshot's visual patterns—router, loop, parallel fan-out, join, human input, state updates, and sub-workflow calls—map well to OpenCompany's planned orchestration. The visual builder itself is not evidence that any workflow, model, MCP server, or integration is connected.

## Why LangGraph is a good fit

The official LangGraph documentation describes it as a low-level orchestration runtime for long-running, stateful agents. It supports deterministic and model-driven steps in one graph, persistence/checkpoints, streaming, and human-in-the-loop execution.

Its checkpointer model saves graph state at super-step boundaries and associates it with a thread. This can support recovery, review, and continuation. Interrupts can pause a graph for external input and resume it later.

Useful mapping to OpenCompany:

| Visual pattern | OpenCompany capability | Intended use |
|---|---|---|
| Start / End | Task lifecycle | Enter and complete a durable task |
| Router | Department/agent dispatcher | Assign research, product, engineering, growth, or support work |
| Loop | Bounded retry/review cycle | Rework only within retry and time budgets |
| Parallel fan-out | Concurrent agents | Independent research or QA tasks |
| Join | Result aggregation | Validate and combine specialist outputs |
| Human input | Central approval service | Pause before protected external actions |
| Call workflow | Reusable subgraph | Invoke a bounded department workflow |
| Set state | Shared task context | Pass typed, traceable outputs between agents |
| Model nodes | Provider-neutral model adapter | Route to explicitly configured providers |

## Non-negotiable architecture boundaries

1. **AIOS remains the system of record.** Tasks, owners, approvals, audit events, business state, and external-action idempotency keys remain in OpenCompany's database and services.
2. **LangGraph is an execution/orchestration layer only.** A graph interrupt is a pause mechanism, not proof of owner approval. The graph must call the central AIOS approval service and resume only after an authenticated decision.
3. **No duplicate sources of truth.** Persist a stable AIOS task ID and graph thread ID mapping. Graph checkpoints may hold execution state, not authoritative payment, order, or approval state.
4. **MCP is a tool-connection protocol, not the workflow engine.** Add MCP servers through an explicit allowlist, scoped credentials, tool schemas, timeouts, audit records, and approval policies. Do not auto-connect every available MCP provider.
5. **Model providers stay replaceable.** Nodes call the AIOS model adapter; no graph node should hard-code a vendor API key or assume a free tier is unlimited.
6. **External actions are idempotent and gated.** Publishing, spending, customer communication, purchases, refunds, production changes, and commitments require an approved action record, replay protection, and an audit trail.
7. **Bound every loop and fan-out.** Enforce max steps, wall-clock deadlines, concurrency limits, token/cost ceilings, cancellation, and retry classification.
8. **Keep the runtime optional.** The task queue and API must remain usable if LangGraph is not installed or unavailable.

## Integration sequence

Do not add the runtime dependency until these prerequisites are complete:

1. Repair and test the current worker package; the current `worker_service.py` imports `agent_runtime`, `model_adapter`, and `worker`, but those modules are absent from the current default-branch file tree.
2. Complete task assignment, dependency handling, leases, retries, timeouts, cancellation, and execution/audit logs in the AIOS core.
3. Define typed agent inputs/outputs and a registry. Agents must not receive unrestricted host or account credentials.
4. Complete a provider-neutral model adapter with disabled-by-default paid providers and explicit request/cost limits.
5. Centralize human approval and verify that a denied, expired, or missing approval cannot execute an external action.
6. Add a LangGraph adapter behind an optional extra/dependency. Start with deterministic mock nodes and the existing AIOS task/approval APIs.
7. Persist graph checkpoints in a supported durable store and test process restart, resume, duplicate dispatch, partial parallel failure, and interrupted approval. Do not assume an in-memory checkpointer is durable.
8. Compare a complete test workflow against the existing queue before enabling real model calls or external tools.

## Storage and hosting caution

The current deployment guide describes a small free hosting profile (512 MB RAM, one CPU, 1 GB storage), subject to provider availability. This is a lightweight API target, not a validated host for a heavy multi-agent runtime. LangGraph's official documentation lists SQLite checkpointing for lightweight/demo use and Postgres checkpointing for production workloads. Do not add a paid database or hosted agent platform without owner approval. First verify whether the existing host's persistent storage and resource limits can support the intended workload.

Do not add LangSmith/Agent Server as a requirement. The core integration must remain self-hostable and useful without a paid observability or deployment service.

## Acceptance tests before declaring integration operational

- A Researcher, Developer, and Quality Reviewer complete a real task through shared state without manual copying.
- A run survives process termination and resumes from durable state without losing completed work.
- Parallel branches join deterministically; a failed branch is retried or marked failed without duplicating successful external work.
- Every step is correlated to an AIOS task ID, agent identity, model/provider, timestamps, and structured output.
- An approval-required action pauses; rejection never executes it; approval resumes exactly once.
- A missing/invalid provider, rate limit, timeout, or malformed model output is handled without crashing the worker.
- No paid provider or metered tool is called unless explicitly enabled and approved.
- The workflow remains functional with mocked models and no MCP credentials.
- Removing/disabling LangGraph does not lose AIOS tasks, approvals, or audit records.

## Current status

This is an architecture decision, not an implementation claim. At the time of this decision, the repository is still a FastAPI/SQLite starter. Its README states that external AI providers, background workers, ecommerce, and social integrations are not connected. The current tree does not contain a complete LangGraph runtime, MCP registry, or verified end-to-end agent workflow.

## Official references

- LangGraph overview: https://langchain-ai.github.io/langgraph/
- Persistence and checkpointers: https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/checkpointers.mdx
- Human-in-the-loop interrupts: https://langchain-ai.github.io/langgraph/concepts/interrupts/
- Checkpoint saver reference: https://langchain-ai.github.io/langgraph/reference/checkpoints/
