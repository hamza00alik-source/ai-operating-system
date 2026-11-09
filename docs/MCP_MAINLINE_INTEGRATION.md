# Mainline MCP integration

This branch ports the MCP connection foundation onto the current mainline agent
runtime without replacing the existing specialist/collaborator/CEO workflow.

## Included now

- Owner-key-protected MCP server registration, listing, enable/disable and
  read-only connection-test endpoints.
- Credentials are referenced only by environment-variable names; secret values
  are never accepted in the registry request or returned by the API.
- Servers are disabled by default and must be explicitly enabled by the owner.
- Connection tests perform only the MCP initialize handshake and tools/list.
  They do not invoke tools.
- DNS answers are resolved once, all addresses must be public, and the HTTPS
  socket is pinned to a validated IP while TLS SNI/certificate verification
  retain the original hostname. Environment proxies are disabled and redirects
  are rejected.
- MCP JSON-RPC response bodies are capped at 1 MB.
- Server registration and enable/disable actions are recorded in an immutable
  audit log.

## Deliberately not enabled in this milestone

- Agent-driven tool discovery or tool-call proposals.
- Owner approval records for individual tool calls.
- Any tool execution endpoint or automatic external action.
- Department allowlists, tool-risk classification, or sandboxing.

The existing company agent runtime remains unchanged. This keeps MCP server
connection management separate from agent execution until the approval and
one-time execution boundary has been ported and tested against the current
mainline schema. Do not enable a server until the owner has configured the
referenced environment credential and reviewed the endpoint.
