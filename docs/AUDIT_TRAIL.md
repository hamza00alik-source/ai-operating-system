# Audit trail

The application records an append-only event for task creation and approval lifecycle changes.

Current event types:
- `task.created`
- `approval.requested`
- `approval.approved`
- `approval.rejected`

Events are stored in the same SQLite database and transaction as the corresponding business change. This means a task or approval mutation and its audit record commit or roll back together.

The internal `list_audit_events(limit=100)` service function returns newest events first. The limit is clamped to 1–500. There is intentionally no public audit endpoint yet; the API currently has a single owner API key rather than a role/permission system.

This is an operational audit foundation, not tamper-proof or externally replicated logging. Production deployments still need backups, restricted filesystem access, retention policy, and a security review.
