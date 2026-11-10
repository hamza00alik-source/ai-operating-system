# Supabase readiness audit

Audit date: 2026-11-10
Project: `ai-operating-system`
Project ref: `biulsnipopormcthqlyr`
Region: `ap-southeast-2`
PostgreSQL: `17.11.0.018`

## Verified read-only findings

- Supabase Management API reports the project as `ACTIVE_HEALTHY`.
- A direct read-only SQL probe (`SELECT 1`) succeeded.
- `public` contains zero application base tables; Supabase reports zero recorded migrations.
- Supabase health and performance advisors returned no findings.
- The security advisor reports both anonymous and authenticated execution warnings for `public.rls_auto_enable()`.
- Catalog inspection confirms `public.rls_auto_enable()` is a `SECURITY DEFINER` function with `search_path = pg_catalog`, attached to the enabled `ensure_rls` event trigger for `ddl_command_end`. The function's body enables RLS on newly created tables in `public`.
- The function ACL includes EXECUTE for `PUBLIC`, `anon`, `authenticated`, and `service_role`. The security advisor explicitly reports the function as reachable through `/rest/v1/rpc/rls_auto_enable`. This is unnecessary public RPC exposure for an internal DDL event-trigger function and should be remediated. Do not drop or disable the event trigger.
- Read-only inspection of `pg_default_acl` found default grants to `anon`, `authenticated`, and `service_role` on public tables, functions, and sequences for both `postgres` and `supabase_admin`. This is the observed project state; do not assume newer Supabase Data API defaults have already been applied to this project.
- Railway production's `aios-api` is online. Its configured variable names include `AI_OS_DATABASE_URL`, but the connected Railway integration redacts its value. Therefore the Railway-to-this-Supabase connection is not verified.
- Railway's current `aios-api` deployment is still configured from branch `feature/owner-dashboard-account-connections-synced`, not `feature/supabase-owner-integration`. The new owner-only Supabase diagnostic routes in PR #101 are therefore not yet available on production. Runtime DNS/network logs from the inspected deployment did not establish a connection to this Supabase host. The absence of an observed outbound DNS/DB flow is not proof of the exact configured URL.

## Schema inventory and migration validation

The detailed source-derived schema, including columns, defaults, primary keys, foreign keys, unique/check constraints, 23 named indexes, and compatibility ALTER TABLE steps, is documented in [SUPABASE_SCHEMA_INVENTORY.md](SUPABASE_SCHEMA_INVENTORY.md). The inventory identifies 22 application tables: `tasks`, `approvals`, `discovery_scans`, `provider_catalog_entries`, `research_sources`, `provider_credentials`, `business_integration_credentials`, `agent_runs`, `agent_run_events`, `agent_run_steps`, `brain_experiences`, `brain_memories`, `owner_sessions`, `business_records`, `investor_contacts`, `code_assets`, `license_offers`, `department_messages`, `department_delegations`, `discovery_candidates`, `workflow_instances`, and `workflow_steps`.

The standalone baseline is `supabase/migrations/20261110160000_aios_initial_schema.sql`. It creates the 22 source-derived tables and 23 indexes and explicitly enables RLS on all 22 tables. It is intended for an empty/new AIOS database and has not been applied to the connected Supabase project. It creates no Data API grants or row policies.

**Baseline CI validation passed:** GitHub Actions run [#42781234481](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781234481), commit `2d3cb610ab608eb406b9b35f185f4e0514d0bfb6`, passed the full application suite and isolated PostgreSQL 16 integration job. The PostgreSQL test applied the baseline to a disposable CI database, verified exactly 22 public tables, 23 named indexes, RLS enabled on all 22 tables, then exercised application initializer compatibility, table metadata inspection, named-parameter task insertion/selection, and discovery scan creation.

**Latest CI validation passed:** GitHub Actions run [#42807313235](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42807313235), commit `e6b94652c4aa7d3837285492bf9ce697a8326cbc`, passed both the full application suite and the PostgreSQL integration job. The integration test creates a disposable event trigger, revokes direct EXECUTE from `PUBLIC`, `anon`, and `authenticated` after registration, verifies those roles no longer have function EXECUTE privilege, then creates a table and confirms the already-registered event trigger still fires. This demonstrates the PostgreSQL 16 behavior needed for a safe ACL remediation design; it does not modify or test the live Supabase function.

The documentation updates also passed both CI workflows: GitHub Actions runs [#42781484052](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781484052) and [#42781494089](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781494089), commit `f1100f61b6645f80e872fedddae6614ffcc5e04e`.

This is evidence that the baseline and event-trigger ACL behavior pass in an isolated PostgreSQL 16 CI environment. It is not a live Supabase migration test and does not prove Railway connectivity.

The runtime SQL scan found SQLite named placeholders in task, business-record, asset, and discovery operations. The PostgreSQL adapter now translates `:name` bindings to psycopg's `%(name)s` format and has regression coverage.

## Interpretation and next gates

The Supabase project is reachable from the Supabase management integration, but it is currently an empty application database. The existence of `AI_OS_DATABASE_URL` in Railway does not prove it points to this project.

PR #101 adds owner-only status and read-only connection-test routes. It is open and draft, and its branch is not deployed to Railway production. The routes have unit tests for a five-second TLS-required `SELECT 1`, sanitized errors, and owner authentication. Production connectivity still needs to be checked through those routes after the PR is reviewed, merged with owner approval, and deliberately deployed.

Do not apply the baseline or switch the live Railway database until the baseline is reviewed, Supabase-specific security items are addressed, a verified backup/rollback plan exists, and the owner separately approves the production change.

## Security recommendation

Treat the `rls_auto_enable()` finding as a real API-surface issue, not a reason to disable RLS automation. Isolated PostgreSQL 16 CI verified that revoking direct EXECUTE privileges after event-trigger registration does not prevent the registered event trigger from firing. The narrowly scoped remediation candidate is to revoke direct function execution from `PUBLIC`, `anon`, `authenticated`, and `service_role`, while leaving `ensure_rls` enabled. This has not been run on Supabase. Apply only after owner approval and re-run Supabase advisors.

The project also retains default grants for `anon`, `authenticated`, and `service_role` on public tables, functions, and sequences. Prepare a separate, reviewed default-privilege hardening plan for both `postgres` and `supabase_admin` before creating application objects. Keep application data access on the trusted backend database connection unless a separate, intentionally designed Data API/RLS model is approved.

## Actions deliberately not performed

- No tables, policies, functions, triggers, grants, or migrations were created or changed in Supabase.
- No production Railway variables were changed.
- No data was imported or migrated.
- No production database switch, PR merge, or deployment was triggered.
