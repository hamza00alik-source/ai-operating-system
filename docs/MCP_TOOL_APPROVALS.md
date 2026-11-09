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

**An approval is not execution permission.** This milestone does not invoke MCP tools, resume an agent, or expose an execution endpoint. The API always reports `execution_enabled: false`. A later milestone must implement tool metadata/schema verification, risk policy, atomic one-time execution consumption, process isolation and pause/resume before any remote tool can run.

The agent's three-stage text runtime is not yet connected to proposal generation. This module is a persistence and owner-review foundation only. No live MCP server is contacted by tests.
