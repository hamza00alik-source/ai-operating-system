# Authentication and audit trail

## Owner API token

- Configure `AI_OS_API_TOKEN` with a random secret of at least 32 characters.
- Send it as `Authorization: Bearer <token>` (or `X-API-Key`).
- `/health` is the only unauthenticated route.
- In `AI_OS_ENV=production`, missing or weak token configuration fails closed with HTTP 503.
- In local development, authentication is optional only for a loopback/local-only instance. Do not expose an unauthenticated development server to the internet.
- This is a single-owner API gate, not a user-account system, multi-tenant RBAC, or a substitute for HTTPS and host firewall rules.

Generate a token locally with Python:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Set it as an environment variable in the server's private environment. Never commit it to Git, paste it into issues, or put it in a frontend bundle.

## Audit trail

API requests (except health checks) are recorded in SQLite without request bodies, authorization headers, or other credentials. Each event includes actor, action, resource, status/request ID metadata and a SHA-256 link to the previous event. The API exposes:
- `GET /audit?limit=100`
- `GET /audit/verify`

The hash chain makes accidental or unauthorized edits detectable; it is not tamper-proof against an attacker who can rewrite the database and recompute the chain. Protect the database file, back it up, and export signed/off-host checkpoints before treating it as forensic evidence.

## Still required before internet exposure

- TLS/HTTPS and reverse-proxy hardening
- Secret rotation and recovery procedure
- Per-role authorization and separate worker credentials
- Rate limiting and login/credential abuse monitoring
- Database backup/restore tests
- Security review of every external integration
- Transactional audit coupling for high-impact actions

Publishing, spending, purchases, customer commitments, refunds, and production changes must remain behind explicit human approval. An audit record is not an approval.
