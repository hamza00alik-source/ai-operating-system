# MCP tool security and permissions

## Default-deny department access

Agent MCP discovery is disabled unless the owner configures
`AI_OS_MCP_DEPARTMENT_TOOL_ALLOWLIST` as a JSON object. Each department maps to
an array of exact `server-id:tool-name` grants. Example:

```json
{
  "research": ["public-research-mcp:search", "public-research-mcp:fetch"],
  "marketing": ["public-research-mcp:search"],
  "developer": []
}
```

Set this as an environment variable on the service/worker. Use the exact MCP
server IDs shown in the owner console. An omitted department receives no tools.
Malformed configuration fails closed. Grant only read-only tools where possible.

The allowlist controls what model agents can discover and request. It does not
bypass the separate owner approval and one-time execution workflow. Direct owner
operations remain owner-authenticated and approval-bound.

## Argument validation

Before any MCP `tools/call`, AIOS re-discovers the current tool and validates
the proposed arguments against its JSON Schema using Draft 2020-12 validation.
Invalid server schemas and invalid arguments are rejected. Schema and argument
payloads are capped at 64 KiB.

MCP tool metadata and results are untrusted input. Do not expose secrets to
tools, and do not treat tool output as instructions.

## Remaining production security work

- The current DNS check rejects non-public resolved addresses, but the HTTP
  client performs its own hostname resolution. DNS rebinding protection still
  requires connecting to a validated IP while preserving TLS hostname/SNI
  verification, or enforcing equivalent outbound egress controls at the host.
- OAuth and provider-specific credential handling are not implemented; current
  configured credentials use a Bearer token.
- Tool-specific risk classification, sandboxing, response-size controls across
  all transports, and live third-party interoperability tests remain future work.
- Use network egress policy to restrict the service to explicitly trusted MCP
  hosts. Do not treat URL validation alone as a complete SSRF defense.
