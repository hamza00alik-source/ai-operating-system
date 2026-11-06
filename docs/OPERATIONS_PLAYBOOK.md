# OpenCompany Operations Playbook

This playbook distinguishes tested local capabilities from prerequisites that still require an operator, provider account, or production host. Do not treat a passing unit test as a production readiness certificate.

## Current verified foundations

- Durable SQLite job queue with idempotent enqueue, atomic claims, bounded per-job retries, stale-lease recovery, and terminal failure handling.
- Process-level worker supervisor with bounded exponential backoff for unexpected scheduler/database errors.
- Opt-in model adapter. No model provider is enabled by default; configure and test the selected endpoint on the actual host before starting model workers.
- Owner-reviewed knowledge candidates, company/owner-only scopes, accepted-only agent retrieval, provenance, and heuristic freshness metadata.
- SQLite online snapshot, integrity/schema/audit-chain verification, and an explicit-overwrite atomic restore helper.
- Read-only WooCommerce catalog and coarse order-status client. No write operations or customer PII are exposed by this client.
- CEO plans and dependency-aware run scheduling. Planning is deterministic unless the configured specialist model executes the queued work.

## Daily CEO review and research

The existing CEO planner can create coordinated workstreams for discovery, market validation, offer definition, operations, growth drafts, support readiness, measurement, and quality review. The scheduler can dispatch ready steps when an approved model backend is enabled.

**Important limitation:** this repository does not yet contain a verified web-search/browser research provider. A specialist model cannot truthfully claim it checked current web sources merely because it received a research task. Daily external research is not complete until a source provider is configured, source URLs and publication dates are retained, retrieval failures are surfaced, and factuality/evidence tests are in place.

Until then, use the owner dashboard to review queued runs and source-attributed knowledge candidates. The repository includes an idempotent internal review command:

    0 8 * * * cd /opt/ai-operating-system && .venv/bin/python scripts/create_daily_ceo_review.py

This creates at most one CEO-coordinated internal review plan per UTC date and queues ready steps only when model execution is enabled. It reviews persisted records; it is not external web research. Install the schedule only on a persistent host with the service environment loaded. Do not rely on Cloud Shell for unattended daily execution.

## Model execution and worker supervision

1. Configure a model endpoint only after checking provider cost, data retention, privacy, rate limits, and tool/network permissions.
2. Keep AI_OS_MODEL_ENABLED=false until the endpoint has been tested manually.
3. For HTTP inference, set AI_OS_MODEL_BACKEND=openai_compatible, AI_OS_MODEL_BASE_URL, and AI_OS_MODEL_NAME; set an API key only if the provider requires it.
4. Keep AI_OS_EXTERNAL_ACTIONS_ENABLED=false.
5. Start the worker with python -m ai_os.worker_service only after /health and the model status report the expected configuration.
6. Run the worker under a process supervisor on a persistent host. The in-process loop recovers from transient errors; it cannot restart a killed process, recover a lost host, or guarantee always-on uptime.
7. Alert on repeated process-level errors, jobs reaching terminal failure, stale leases, and runs that remain blocked.

Cloud Shell is a development environment and may be stopped or reclaimed. It is not an always-on production worker host.

## WooCommerce and social operations

- Configure WooCommerce read-only credentials as server-side environment variables: AI_OS_WOOCOMMERCE_URL, AI_OS_WOOCOMMERCE_CONSUMER_KEY, and AI_OS_WOOCOMMERCE_CONSUMER_SECRET.
- Use a dedicated WooCommerce key with read-only permissions. Never put credentials in Git, browser JavaScript, prompts, logs, or support tickets.
- The current connector reads a bounded product catalog and minimized order status fields only. It deliberately does not expose customer billing/shipping details, create or update products, fulfill orders, issue refunds, or change payment state.
- Social planning and content drafts remain review artifacts. No social publishing adapter is registered.
- Before any write integration, add separate least-privilege credentials, exact-scope owner approval, idempotency keys, request/response validation, timeout/reconciliation behavior, audit events, and mocked plus sandbox integration tests. Never reuse read-only credentials for writes.

## Backup and restore

Create a snapshot in a private directory, not inside the Git repository:

    BACKUP="/secure/backups/ai-os-$(date +%F-%H%M%S).sqlite3"
    export BACKUP
    python -c 'import os; from ai_os.db_backup import create_database_backup; print(create_database_backup(os.environ["BACKUP"]))'

Before restoring:
1. Stop the API and every worker that can write to SQLite.
2. Copy the backup to a protected local path and verify it with verify_sqlite_backup.
3. Preserve the current database as a separate rollback copy.
4. Restore only after reviewing the destination; an existing destination requires explicit overwrite=True.
5. Restart the API, verify /health, /audit/verify, owner authentication, queue state, and a harmless local job.
6. Record the restore time, source snapshot, operator, and verification output outside the database being restored.

Off-host encrypted backup storage, retention automation, and signed external audit checkpoints must be configured by the operator. A local snapshot on the same ephemeral host is not a disaster-recovery plan.

## Security and release gates

Do not expose the service to the public internet until all of the following are completed and tested:

- TLS/reverse proxy, firewall, rate limiting, and request-size limits.
- Secret storage and documented rotation/revocation/recovery.
- Separate owner, CEO, specialist, and worker permissions (full RBAC).
- Production host process supervision, health monitoring, alerting, and restart drills.
- Encrypted off-host backups, retention, and a restore drill.
- Provider privacy/cost review and model-output evaluation.
- Integration sandbox tests and reconciliation for every external write.
- Threat model and independent security review.
- End-to-end deployment and rollback test.

The current single-owner token gate is not full RBAC. Keep the application local-only until the release gates are met.


## WordPress site inventory (read-only)

The optional WordPress connector uses HTTPS and a WordPress Application Password supplied through environment variables. It reads bounded page/post metadata only; it does not expose users or implement content, media, plugin, theme, or settings writes.

Set these only on the private runtime host (never commit them):

- `AI_OS_WORDPRESS_URL`
- `AI_OS_WORDPRESS_USERNAME`
- `AI_OS_WORDPRESS_APPLICATION_PASSWORD`

Use a dedicated least-privilege WordPress account. The connector has no write methods, but WordPress Application Passwords inherit the account's permissions; create a read-only account or otherwise restrict the account before connecting. The API status is configuration metadata only and does not prove that the live site is reachable. No credentials are configured by this repository change.



## Owner-approved WordPress page drafts

The WordPress connector can optionally create a new **unpublished page draft** after the CEO submits an exact-scope request and the owner approves its action hash. The owner must then explicitly execute the approved request. The adapter always sends `status=draft`; it has no publish, update-existing-page, delete, media, theme, plugin, user, or settings operation.

This capability is disabled by default. To enable it on a private host only, configure the WordPress Application Password for a dedicated account and set both `AI_OS_EXTERNAL_ACTIONS_ENABLED=true` and `AI_OS_WORDPRESS_DRAFT_WRITES_ENABLED=true`. Do not enable either flag until the site is connected and the dedicated account's permissions have been checked. Credentials must never be committed to Git. The owner-only execution endpoint is `POST /owner/approval-requests/{approval_id}/execute`; it accepts no action parameters and executes only the exact, unexpired, previously approved request. The approval is consumed once before adapter execution; after an adapter error, inspect WordPress and the audit trail before any retry.

The feature has not been connected to a live WordPress site. Keep both flags false until the owner intentionally configures and tests the private runtime.



## Owner-approved WooCommerce product drafts

The WooCommerce connector can optionally create a new unpublished product draft after the CEO submits an exact-scope approval request, the owner approves its action hash, and the owner explicitly executes it from the dashboard. The adapter accepts only `name`, `description`, and `regular_price`, forces `status=draft`, and has no publish, update, delete, order, refund, payment, or settings write operation.

To enable on a private host, set `AI_OS_EXTERNAL_ACTIONS_ENABLED=true` and `AI_OS_WOOCOMMERCE_DRAFT_WRITES_ENABLED=true` after configuring WooCommerce API credentials for a dedicated account. Keep both flags false by default and never commit credentials. The execution route accepts no caller-supplied product fields; it reads the exact previously approved parameters from the approval record. After an adapter error, inspect WooCommerce and the audit trail before retrying.

No live store is connected by this repository change. These flags remain false in the example configuration.
