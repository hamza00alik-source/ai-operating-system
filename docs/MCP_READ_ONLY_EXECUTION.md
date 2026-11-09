# Read-only MCP execution

This feature adds a separate owner-triggered execution step after an MCP proposal has
been approved. It does not enable autonomous tool execution.

## Required environment configuration

Keep the existing department allowlist, for example:

```env
AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST={"research":["research-mcp:search"]}
```

Add a second, narrower allowlist containing only tools the owner has independently
reviewed as read-only:

```env
AI_OS_MCP_READ_ONLY_TOOLS=["research-mcp:search"]
```

Use exact `server-id:tool-name` values. An empty or invalid value denies execution.
Do not add write, publish, send, payment, account-management, or customer-contact tools.

The server must also include `annotations.readOnlyHint: true` for the tool in its
fresh `tools/list` response. The executor compares the live input schema with the
persisted owner-discovered schema and revalidates the approved arguments immediately
before calling the tool. A changed schema, disabled server, missing grant, expired
proposal, or missing read-only annotation blocks the call.

## Owner workflow

1. An agent may create a proposal; it cannot invoke the MCP tool.
2. The owner reviews the exact server, tool, arguments, and expiry.
3. The owner approves or rejects the proposal.
4. Only after approval, the owner may call
   `POST /integrations/mcp/proposals/{proposal_id}/execute` using owner authentication.
5. The approval is consumed before the network call. Failed or interrupted attempts
   cannot be replayed; create and review a new proposal instead.

The endpoint is owner-authenticated. The tool result is returned to the owner, while
the immutable audit log stores execution metadata and a result hash rather than the
full result payload.

## Current boundaries

- Only explicitly configured read-only tools are eligible.
- A live `readOnlyHint` annotation is required in addition to the owner allowlist.
- No write-capable MCP tool is enabled by this feature.
- No proposal is executed automatically when it is approved.
- No customer-facing action, publication, message, purchase, payment, or account
  change is authorized.
- This feature branch is not deployed or merged by this change.

A read-only annotation is a server assertion, not a cryptographic guarantee. Only
connect MCP servers the owner trusts, and review each tool before adding it to the
read-only allowlist.
