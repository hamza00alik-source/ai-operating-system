# OpenCompany production operations runbook

Status: preparation guidance only. No production environment has been inspected or changed by this document.

## Before any production release

1. Confirm the target repository, branch, commit SHA, deployment service, environment and persistent volume with the owner.
2. Confirm the owner API key and independent secret-encryption key are stored only in the hosting provider's secret manager.
3. Back up the encryption key securely. Losing or rotating it without a planned re-encryption procedure makes stored provider credentials unreadable.
4. Confirm the database path is on a persistent volume, not the container filesystem.
5. Confirm the owner can authenticate, the audit chain verifies, the SQLite integrity check passes, and the production-evidence endpoint reports the expected database and configuration checks.
6. Complete the full authenticated mobile-browser acceptance checklist and independent security review.
7. Obtain explicit owner approval for the exact production commit and deployment action. A green CI run is not deployment authorization.

## Backup procedure

1. Stop or pause worker execution through the owner console before a maintenance backup when operationally safe.
2. Authenticate as the owner and download `GET /owner/backup` over HTTPS.
3. Store the downloaded SQLite backup in a protected off-host location with restricted access and retention.
4. Record the backup timestamp, source environment, source commit, schema version and file checksum in the operator's protected records.
5. Never attach the backup to a public issue, pull request, chat, or public artifact. It may contain confidential business and customer data.

The endpoint uses SQLite's online backup API and checks the resulting snapshot's integrity. It does not encrypt the downloaded backup file; protect it as sensitive data.

## Isolated restore rehearsal

1. Create an isolated staging environment with no customer-facing traffic and no external write credentials.
2. Restore a copy of the backup to a new database path. Do not overwrite the live database.
3. Configure the same secret-encryption key used by the source database, through the staging secret manager only.
4. Open the restored database with the exact application version intended for recovery.
5. Verify `PRAGMA integrity_check` returns `ok`, the schema version is supported, and the audit chain validates.
6. Verify business-scoped records, owner login, workflow reads and worker state. Keep workers stopped.
7. Record observed recovery time and the age of the restored backup to establish measured RTO/RPO.
8. Destroy the isolated test copy using the hosting provider's approved secure data-retention procedure after recording results.

The automated test suite proves that a generated SQLite snapshot can be reopened and its integrity/audit chain checked. It does not replace a production-volume restore rehearsal or prove a measured RTO/RPO.

## Incident and rollback controls

- Pause workers before database maintenance or suspected data corruption.
- Preserve the original database and logs before attempting repair.
- Never run destructive schema repair or delete data as an improvised recovery action.
- Restore to a new path first and validate it before any cutover.
- Require explicit owner approval before changing the live database path, restoring over production data, rotating encryption keys, changing service routing or redeploying.
- After an approved recovery, verify owner authentication, audit chain, database integrity, business isolation, queue leases and external integrations before resuming workers.

## Current limitations

- Automated off-host backup scheduling and retention are not implemented.
- Production restore rehearsal and measured RPO/RTO are not verified.
- Independent security review, production monitoring/alerting and incident exercises remain release gates.
- The owner backup endpoint returns a SQLite file but does not encrypt it.
- The production-readiness endpoint is an evidence snapshot only; it never authorizes a release.
