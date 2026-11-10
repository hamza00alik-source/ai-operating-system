# Supabase readiness audit

Audit date: 2026-11-10
Project: `ai-operating-system`
Project ref: `biulsnipopormcthqlyr`
Region: `ap-southeast-2`

## Verified read-only findings

- Supabase Management API reports the project as `ACTIVE_HEALTHY`.
- A direct read-only SQL probe (`SELECT 1`) succeeded.
- No application tables were found in the `public` schema.
- Supabase reports no recorded database migrations.
- Supabase health and performance advisors returned no findings.
- The security advisor reports that `public.rls_auto_enable()` is a `SECURITY DEFINER` function with direct EXECUTE access for `anon` and `authenticated`.
- Catalog inspection confirms the function is attached to the enabled `ensure_rls` event trigger for `ddl_command_end`. Its body enables RLS on newly created tables in `public`; it does not create application tables or policies.
- Railway production's `aios-api` is online. Its configured variable names include `AI_OS_DATABASE_URL`, but the connected Railway integration does not expose the value. Therefore the Railway-to-this-Supabase connection is not verified by this audit.

## Interpretation

The Supabase project is reachable from the Supabase management integration, but it is currently an empty application database. The existence of `AI_OS_DATABASE_URL` in Railway does not prove it points to this project.

The detailed source-derived schema, including columns, defaults, primary keys, foreign keys, unique/check constraints, 23 named indexes, and compatibility ALTER TABLE steps, is documented in [SUPABASE_SCHEMA_INVENTORY.md](SUPABASE_SCHEMA_INVENTORY.md). The source inventory identifies 22 application tables: `tasks`, `approvals`, `discovery_scans`, `provider_catalog_entries`, `research_sources`, `provider_credentials`, `business_integration_credentials`, `agent_runs`, `agent_run_events`, `agent_run_steps`, `brain_experiences`, `brain_memories`, `owner_sessions`, `business_records`, `investor_contacts`, `code_assets`, `license_offers`, `department_messages`, `department_delegations`, `discovery_candidates`, `workflow_instances`, and `workflow_steps`. The first 20 are initialized in `src/ai_os/db.py`; the final two are initialized in `src/ai_os/workflows.py`. The source also contains backward-compatible ALTER TABLE steps and indexes which must be represented in a baseline. This remains a source-code inventory, not a verified database schema export or executable migration. Runtime SQL compatibility and PostgreSQL integration tests are still pending. Do not point the live Railway service at this empty database until the full schema and all runtime-created tables have been inventoried, a migration baseline has been generated and reviewed, and a backup/rollback plan exists.

## Security recommendation

The initial idea to revoke EXECUTE from `public.rls_auto_enable()` has been withdrawn and its draft migration removed. Although the security advisor flags the SECURITY DEFINER function, it is bound to a database event trigger. Changing its execution ACL without validating PostgreSQL event-trigger invocation semantics could disrupt automatic RLS enforcement. Leave the function and event trigger unchanged until a safe, verified remediation is established.

## Actions deliberately not performed

- No tables, policies, functions, triggers, or migrations were created or changed in Supabase. No production schema migration has been generated or applied.
- No production Railway variables were changed.
- No data was imported or migrated.
- No production database switch or deployment was triggered.
