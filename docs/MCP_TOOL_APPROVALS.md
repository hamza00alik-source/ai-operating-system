# MCP tool proposal approval inbox

This milestone adds a persisted, owner-only approval inbox for proposed MCP calls.

## Current behavior

- Worker-side code may call `propose_tool_call(...)` to persist a proposal.
- Proposals are accepted only when `AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST` explicitly maps the department to the exact `server-id:tool-name` identifier. Missing or invalid configuration fails closed.
- Arguments are limited to 64 KiB and stored as canonical JSON with a SHA-256 fingerprint.
- Proposals expire after 30 minutes by default (configurable per call, capped at 24 hours).
- The owner can inspect proposals at `GET /integrations/mcp/proposals` and decide once at `POST /integrations/mcp/proposals/{id}/decision`.
- The inbox and decision routes require owner authentication.

Example allowlist:

```json
{"research":["research-mcp:search"]}
```

## Critical boundary

**An approval is not execution permission.** This milestone does not invoke MCP tools, resume an agent, or expose an execution endpoint. The API always reports `execution_enabled: false`. The separate `reserve_approved_tool_proposal(...)` primitive atomically reserves an approved proposal exactly once after rechecking its fingerprint, expiry, current enabled-server schema, argument validity and department allowlist. The reservation is audit-logged and replay-protected by a unique proposal constraint. It is only a checkpoint for a future executor: it does not load credentials, make a network request, change the approval decision, or enable execution. The remaining work is isolated execution, resource/time/output limits, result persistence and safe agent resumption, followed by a separate security review and owner authorization.

The agent's three-stage text runtime is not yet connected to proposal generation. This module is a persistence and owner-review foundation only. No live MCP server is contacted by tests.
