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

## Schema inventory and migration validation

The detailed source-derived schema, including columns, defaults, primary keys, foreign keys, unique/check constraints, 23 named indexes, and compatibility ALTER TABLE steps, is documented in [SUPABASE_SCHEMA_INVENTORY.md](SUPABASE_SCHEMA_INVENTORY.md). The source inventory identifies 22 application tables: `tasks`, `approvals`, `discovery_scans`, `provider_catalog_entries`, `research_sources`, `provider_credentials`, `business_integration_credentials`, `agent_runs`, `agent_run_events`, `agent_run_steps`, `brain_experiences`, `brain_memories`, `owner_sessions`, `business_records`, `investor_contacts`, `code_assets`, `license_offers`, `department_messages`, `department_delegations`, `discovery_candidates`, `workflow_instances`, and `workflow_steps`.

The standalone baseline is `supabase/migrations/20261110160000_aios_initial_schema.sql`. It creates the 22 source-derived tables and 23 indexes and explicitly enables RLS on all 22 tables. It is intended for an empty/new AIOS database and has not been applied to the connected Supabase project.

**CI validation passed:** GitHub Actions run [#42781234481](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781234481), commit `2d3cb610ab608eb406b9b35f185f4e0514d0bfb6), completed successfully on 2026-11-10. Both the full application test job and the isolated PostgreSQL 16 integration job passed. The PostgreSQL test applied the baseline to a disposable CI database, verified exactly 22 public tables, 23 named indexes, RLS enabled on all 22 tables, then exercised application initializer compatibility, table metadata inspection, named-parameter task insertion/selection, and discovery scan creation.

This is evidence that the baseline runs in the CI PostgreSQL 16 environment. It is not a live Supabase migration test, does not validate Supabase-specific event-trigger behavior in vanilla PostgreSQL, and does not prove Railway connectivity.

The runtime SQL scan found SQLite named placeholders in task, business-record, asset, and discovery operations. The PostgreSQL adapter now translates `:name` bindings to psycopg's `%(name)s` format and has regression coverage.

## Interpretation and next gates

The Supabase project is reachable from the Supabase management integration, but it is currently an empty application database. The existence of `AI_OS_DATABASE_URL` in Railway does not prove it points to this project.

Do not point the live Railway service at this empty database until the full schema and all runtime-created tables have been inventoried, a migration baseline has been reviewed, a backup/rollback plan exists, and the live connection has been safely tested. The source-derived baseline is now CI-validated but still needs a Supabase-specific validation and owner approval before application.

## Security recommendation

The initial idea to revoke EXECUTE from `public.rls_auto_enable()` has been withdrawn and its draft migration removed. Although the security advisor flags the SECURITY DEFINER function, it is bound to a database event trigger. Changing its execution ACL without validating PostgreSQL event-trigger invocation semantics could disrupt automatic RLS enforcement. Leave the function and event trigger unchanged until a safe, verified remediation is established.

## Actions deliberately not performed

- No tables, policies, functions, triggers, or migrations were created or changed in Supabase. No production schema migration has been applied.
- No production Railway variables were changed.
- No data was imported or migrated.
- No production database switch, PR merge, or deployment was triggered.
