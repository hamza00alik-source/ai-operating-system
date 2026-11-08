# MCP provider catalogue

OpenCompany ships a curated catalogue of 55 integration families at `/integrations/mcp/providers`. The catalogue is metadata only: it does not connect accounts, launch arbitrary packages, or make remote tools executable.

## Live public MCP discovery verification

The read-only CI smoke test successfully connected to the public Streamable HTTP
test server at `https://api.sondahub.com/mcp` and discovered 26 tool definitions.
The test exercised endpoint registration, owner activation, the HTTPS hostname
allowlist, MCP initialization, and `tools/list`. It deliberately did not call
any remote tool. The public test server also advertises write-capable tools, so
its discovery success is not an authorization to execute them. See the
[public MCP test-server documentation](https://sondahub.com/mcp-server/).

The smoke workflow is at
[`.github/workflows/public-mcp-smoke.yml`](../.github/workflows/public-mcp-smoke.yml).
A successful discovery proves protocol connectivity and metadata retrieval only;
it does not prove that a remote tool is safe or that OAuth is configured.

## Connection model

1. The owner selects a provider in the Integrations UI.
2. OpenCompany resolves a concrete MCP server and transport from the official [MCP Registry](https://registry.modelcontextprotocol.io) or the provider's documentation. Catalogue entries are not trusted as executable commands.
3. The owner supplies a scoped bearer token through the encrypted server-side vault. OAuth 2.1 authorization-code flow and refresh are not implemented yet.
4. OpenCompany validates the endpoint, discovers tool metadata, and records the server/tool version.
5. Each tool is mapped to a named agent with an explicit capability grant. Discovery alone never grants execution.
6. Read operations are the default. Writes, messages, publishing, payments, refunds, deployments and destructive operations require an owner approval and an idempotency key, with audit logging.

## Catalogue coverage

Developer platforms (GitHub, GitLab, Git); project management (Linear, Jira, Asana, Trello, Monday.com, Todoist); productivity and communication (Notion, Google Drive, Gmail, Google Calendar, Slack, Discord, Telegram, Twilio, Intercom); design (Figma, Canva); commerce and payments (WordPress, WooCommerce, Shopify, Stripe, PayPal); data (Supabase, PostgreSQL, SQLite, MongoDB, Redis, Neon, BigQuery, Snowflake); observability and cloud (Sentry, Datadog, Vercel, Cloudflare, AWS, Azure, Google Cloud, Docker, Kubernetes); browser automation (Playwright, Puppeteer); research (Fetch, Brave Search, Tavily, Exa, Firecrawl, Perplexity); media and creative tools (YouTube, ElevenLabs, Blender); local tools (Filesystem, Memory).

## Important limitations

- This is a broad curated catalogue, not literally every MCP server. The official registry is the discovery source for additional servers.
- An entry does not mean a provider has a stable hosted MCP endpoint or supports OAuth. Some servers require a local worker, API key, bot token, database connection, or self-hosting.
- The catalogue endpoint currently reports providers and setup modes only. Account connection, encrypted credential storage, OAuth callback handling, registry search/sync, MCP tool execution, and the OpenCompany MCP server are separate implementation gates.
- No credentials belong in this public repository or in client-side browser storage.
- Providers that can incur charges (for example, hosted AI, crawling, voice, cloud or database services) remain disabled until the owner explicitly approves a budget.

## API

- `GET /integrations/mcp/providers`: returns the curated provider catalogue and safe defaults.
- `GET /integrations/mcp/registry/search?q=filesystem&limit=10`: searches the official registry using `version=latest`, bounded to 25 results and an 8-second timeout. It returns a minimal metadata projection; results are labelled unverified, never installable, and never executable. Redirects are not followed and oversized responses are rejected.
- Existing endpoint discovery remains owner-triggered and allowlist-protected. Discovery results remain untrusted and non-executable.

## OpenCompany MCP server

OpenCompany also exposes its own read-only MCP server for compatible clients:

- Install: `pip install -e '.[mcp]'` (the development extra includes the SDK for CI).
- Run: `ai-os-mcp` (stdio transport; launch it as a local MCP server in the compatible host's configuration).
- Tools: `get_company_status`, `list_company_departments`, `list_company_agents`, and `list_mcp_integrations`.
- Resource: `opencompany://governance`.

This initial server is intentionally stdio-only and read-only. It does not expose remote HTTP access or OAuth itself. Remote hosting must add MCP OAuth 2.1 resource-server authorization, protected-resource metadata, origin/host validation, per-agent authorization, rate limits, and audit enforcement before it is exposed to the internet. Do not expose the stdio server through an unauthenticated network tunnel.

## Encrypted credential vault (server-side)

The owner-only credential endpoints are available after deployment configures an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the generated value as `AI_OS_CREDENTIAL_ENCRYPTION_KEY` in the hosting platform's secret manager. Do not commit it, put it in a public issue, or send it in chat. Back it up securely: losing the key makes previously stored credentials unreadable. The vault fails closed when the key is missing or invalid.

- `POST /integrations/mcp/credentials`: accepts provider ID, label, secret type and a JSON secret object; encrypts the secret before persistence and returns only a vault reference.
- `GET /integrations/mcp/credentials`: returns metadata only, never secret values.
- `DELETE /integrations/mcp/credentials/{credential_id}`: revokes a stored credential.
- Internal server code may resolve a vault reference; there is deliberately no API endpoint to retrieve decrypted credentials.
- Production credential submission requires HTTPS. The application owner must also configure TLS correctly at the reverse proxy.
- Remote MCP discovery can now resolve a vault reference containing `{"access_token":"..."}` and send it as an HTTPS `Authorization: Bearer` header. Tokens remain server-side and are not returned to the browser.
- This is static bearer-token authentication only. OAuth 2.1 authorization-code flow, protected-resource metadata discovery, issuer validation, audience/resource binding, refresh tokens, and scoped consent are not implemented yet. A stored token is not proof of a working provider connection.


## Owner-approved read-only tool broker

The control plane now persists discovered MCP tool metadata and exposes a
narrow execution broker:

- `GET /control-plane/mcp/tools` lists persisted discovery results.
- `POST /control-plane/mcp/mappings` requires explicit
  `owner_confirmed_read_only: true` and a tool previously discovered from an
  owner-enabled endpoint.
- `GET /control-plane/mcp/mappings` lists approved mappings.
- `PATCH /control-plane/mcp/mappings/{mapping_id}` pauses or resumes a mapping.
- `POST /control-plane/mcp/mappings/{mapping_id}/execute` requires an enabled
  agent with an explicit `tool.mcp.read` capability grant.

This first broker is deliberately read-only. It validates the JSON argument
object against the discovered schema, re-fetches the remote tool list before
each call and blocks execution if the schema has changed since approval.
Only text results are returned; image, binary and embedded resource content is
rejected. Inputs and outputs are size-limited and execution is time-limited.
No generic write-capable tool execution is exposed. Publishing, customer
messaging, payments, refunds, spending and deployment continue to use separate
owner-approval workflows.

Owner confirmation is a trust decision, not proof that a remote tool is
actually side-effect-free. Review the provider's documentation and tool
description before mapping. A malicious or compromised remote server can
still misrepresent its behavior; do not approve a tool as read-only unless
that risk is acceptable.

Agent runtime integration is now available through the registered `mcp.read`
tool. When `AI_OS_AGENT_TOOL_CALLS_ENABLED=true` and the agent has an explicit
`tool.mcp.read` grant, the model receives only that agent's approved mapping
catalog and may request bounded read-only calls. The default remains disabled.
OAuth 2.1 user authorization, token refresh, and public remote hosting of the
OpenCompany MCP server remain separate implementation tasks. Remote MCP authentication now supports static bearer tokens and OAuth 2.1
client-credentials (machine-to-machine) grants through the MCP SDK. OAuth issuer
hosts must be separately allowlisted; issuer validation and token acquisition
are delegated to the SDK. M2M access-token state is persisted encrypted inside
the same vault record as the client secret; the SDK reuses valid tokens and
obtains a new client-credentials token when needed. User authorization-code/PKCE
consent and CIMD are not yet wired into the dashboard.


### OAuth machine-to-machine credential format

Store this JSON in the encrypted credential vault and select it on the MCP
endpoint:

```json
{
  "client_id": "provider-issued-client-id",
  "client_secret": "provider-issued-client-secret",
  "issuer": "https://auth.provider.example/",
  "scope": "files:read"
}
```

The optional `token_endpoint_auth_method` may be `client_secret_basic` (default)
or `client_secret_post`. Add both the MCP hostname and OAuth issuer hostname
to `AI_OS_MCP_ALLOWED_HOSTS`. The issuer must resolve to public IP addresses
and use HTTPS. Do not put client secrets in endpoint URLs, source files, or
chat. This mode is for providers that explicitly support the client-credentials
grant; it does not replace interactive user consent for account-scoped APIs.
