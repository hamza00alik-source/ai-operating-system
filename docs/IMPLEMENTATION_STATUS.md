# AI Operating System implementation status

Last checked: 2026-11-08. This status describes the feature branch
`feat/multi-storefront-commerce-core`, not the deployed production service.

## Verified in CI

- Full automated test suite passed, including the agent handoff, worker recovery,
  credential vault, MCP safety, commerce and control-plane tests.
- Live public model workflow passed using the no-key OVHcloud
  `gpt-oss-20b` endpoint through AIOS's own model adapter:
  Researcher -> dependent Strategist -> automatic CEO review. The workflow used
  a temporary database and synthetic task; it did not touch stores or customers.
- Live public MCP discovery passed against `https://api.sondahub.com/mcp`:
  HTTPS hostname allowlist, endpoint registration/activation, MCP initialize,
  and tools/list returned 26 tool definitions. No remote tool was invoked.
- Docker image build, API container startup, writable persistent-volume
  smoke test, and separate continuous-worker container startup all passed in CI.

## Implemented foundations

- SQLite durable queue, worker leases, retries, restart recovery and continuous
  worker loop with heartbeat/backoff.
- Dependency-aware specialist work packets now include completed predecessor
  reports as untrusted handoff context.
- Automatic CEO review is queued after specialist and delegated manager work
  is terminal. Proposed draft actions remain pending owner approval.
- Free-only anonymous model preset with exact endpoint/model allowlisting and
  conservative request pacing.
- MCP provider catalogue, official registry metadata search, encrypted
  credential vault, HTTPS host allowlist, static bearer support and
  metadata-only remote discovery.
- Owner-approved read-only MCP tool mappings, per-agent capability grants,
  strict argument checks, live schema-drift checks, text-only bounded results,
  and an opt-in `mcp.read` specialist tool-call adapter.
- Docker Compose API + worker services sharing a persistent data volume.
- Multi-storefront commerce catalogue, listing packets, normalized order
  ledger, webhook verification and manual fulfillment review foundations.

## Not yet production-complete

- MCP OAuth 2.1 authorization-code/PKCE, token refresh and scoped consent.
- Generic write-capable remote MCP tool execution; only owner-approved read-only mappings are supported.
- Public remote hosting for the OpenCompany MCP server; it remains local stdio.
- Live marketplace OAuth/account verification and automated listing publication.
- Automated digital-file hosting, licensing, download delivery and refund/dispute
  reconciliation.
- Production host provisioning, persistent-volume backup/restore, TLS, monitoring
  and independent security review.
- Real WooCommerce webhook/account connection and end-to-end live order test.
- Continuous daily research/CEO operations on a provisioned host.

## Governance

The public model and MCP tests are limited verification tasks. They do not grant
remote tool permissions. Publishing, customer messaging, payments, refunds,
spending, destructive changes and deployment remain behind owner approval.
Never commit API tokens, OAuth secrets, encryption keys or customer data.

## Current pull request state

PR #14 remains a draft and is not merged. Its base is the feature branch
`feat/agent-control-plane`, not `main`. Do not merge or retarget it without
reviewing the full dependency stack.
