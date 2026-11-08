# MCP provider catalogue

OpenCompany ships a curated catalogue of 55 integration families at `/integrations/mcp/providers`. The catalogue is metadata only: it does not connect accounts, launch arbitrary packages, or make remote tools executable.

## Connection model

1. The owner selects a provider in the Integrations UI.
2. OpenCompany resolves a concrete MCP server and transport from the official [MCP Registry](https://registry.modelcontextprotocol.io) or the provider's documentation. Catalogue entries are not trusted as executable commands.
3. The owner completes the provider's OAuth consent or supplies a scoped credential through the future encrypted server-side secret store.
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
