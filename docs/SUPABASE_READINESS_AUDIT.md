# Supabase readiness audit

Audit date: 2026-11-10
Project: `ai-operating-system`
Project ref: `biulsnipopormcthqlyr`
Region: `ap-southeast-2`
PostgreSQL: `17.11.0.018`

## Verified read-only findings

- Supabase Management API reports the project as `ACTIVE_HEALTHY`.
- A direct read-only SQL probe (`SELECT 1`) succeeded.
- The source-derived baseline has been applied: `public` contains 22 AIOS application tables and Supabase records two migrations (the baseline and the narrowly scoped function ACL remediation). All 22 tables currently contain zero rows.
- Supabase health and performance advisors returned no findings.
- The `rls_auto_enable()` function ACL is now restricted to its owner (`postgres`); direct EXECUTE for `PUBLIC`, `anon`, `authenticated`, and `service_role` has been revoked. The `ensure_rls` event trigger remains enabled.
- Catalog inspection confirms `public.rls_auto_enable()` remains a `SECURITY DEFINER` function with `search_path = pg_catalog`, attached to the enabled `ensure_rls` event trigger for `ddl_command_end`. The function's body enables RLS on newly created tables in `public`.
- The function ACL was verified after remediation as `{postgres=X/postgres}`. The event trigger remains enabled. Supabase security advisors no longer report public/anonymous execution of this function.
- Read-only inspection of `pg_default_acl` found default grants to `anon`, `authenticated`, and `service_role` on public tables, functions, and sequences for both `postgres` and `supabase_admin`. This is the observed project state; do not assume newer Supabase Data API defaults have already been applied to this project.
- Railway production's `aios-api` is online after deployment of commit `06f0c989c2e1187f9602547452d8b38e51f081f3`. Its configured variable names include `AI_OS_DATABASE_URL`, but the connected Railway integration redacts its value. The production database target therefore remains unverified and has not been switched.
- The owner-only Supabase diagnostic routes from PR #101 are included in the live production deployment. The Railway connector does not expose variable values or a way to submit an authenticated owner request, so the deployed `POST /integrations/supabase/test` probe still needs to be run from the signed-in Owner Dashboard. Do not infer that the runtime uses this project merely because the variable name exists.

## Schema inventory and migration validation

The detailed source-derived schema, including columns, defaults, primary keys, foreign keys, unique/check constraints, 23 named indexes, and compatibility ALTER TABLE steps, is documented in [SUPABASE_SCHEMA_INVENTORY.md](SUPABASE_SCHEMA_INVENTORY.md). The inventory identifies 22 application tables: `tasks`, `approvals`, `discovery_scans`, `provider_catalog_entries`, `research_sources`, `provider_credentials`, `business_integration_credentials`, `agent_runs`, `agent_run_events`, `agent_run_steps`, `brain_experiences`, `brain_memories`, `owner_sessions`, `business_records`, `investor_contacts`, `code_assets`, `license_offers`, `department_messages`, `department_delegations`, `discovery_candidates`, `workflow_instances`, and `workflow_steps`.

The standalone baseline is `supabase/migrations/20261110160000_aios_initial_schema.sql`. It was applied to the previously empty AIOS Supabase project on 2026-11-10. It creates the 22 source-derived tables and 23 indexes and explicitly enables RLS on all 22 tables. It creates no Data API grants or row policies. Post-migration inspection confirmed all 22 tables exist, all have RLS enabled, and all contain zero rows.

**Baseline CI validation passed:** GitHub Actions run [#42781234481](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781234481), commit `2d3cb610ab608eb406b9b35f185f4e0514d0bfb6`, passed the full application suite and isolated PostgreSQL 16 integration job. The PostgreSQL test applied the baseline to a disposable CI database, verified exactly 22 public tables, 23 named indexes, RLS enabled on all 22 tables, then exercised application initializer compatibility, table metadata inspection, named-parameter task insertion/selection, and discovery scan creation.

**Latest CI validation passed:** GitHub Actions run [#42807313235](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42807313235), commit `e6b94652c4aa7d3837285492bf9ce697a8326cbc`, passed both the full application suite and the PostgreSQL integration job. The integration test creates a disposable event trigger, revokes direct EXECUTE from `PUBLIC`, `anon`, and `authenticated` after registration, verifies those roles no longer have function EXECUTE privilege, then creates a table and confirms the already-registered event trigger still fires. This demonstrates the PostgreSQL 16 behavior needed for a safe ACL remediation design; it does not modify or test the live Supabase function.

The documentation updates also passed both CI workflows: GitHub Actions runs [#42781484052](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781484052) and [#42781494089](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781494089), commit `f1100f61b6645f80e872fedddae6614ffcc5e04e`.

The baseline and ACL changes are now applied to the live Supabase project. The baseline previously passed isolated PostgreSQL 16 CI validation; the live post-migration inspection confirms table count, RLS state and empty row counts. This still does not prove Railway application connectivity.

The runtime SQL scan found SQLite named placeholders in task, business-record, asset, and discovery operations. The PostgreSQL adapter now translates `:name` bindings to psycopg's `%(name)s` format and has regression coverage.

## Interpretation and next gates

The Supabase project is healthy and now has the empty AIOS schema. The existence of `AI_OS_DATABASE_URL` in Railway does not prove it points to this project.

PR #101 was merged and deployed. Its owner-only status and read-only connection-test routes have unit tests for a five-second TLS-required `SELECT 1`, sanitized errors, and owner authentication. Production connectivity still needs to be checked by running the connection test from the signed-in Owner Dashboard.

The baseline is applied, but the Railway production database has deliberately not been switched. Before switching, verify the deployed owner-only connection test, make and verify a backup of the existing Railway SQLite volume, rehearse migration/import and rollback, then confirm schema compatibility.

## Security recommendation

The `rls_auto_enable()` API-surface issue was remediated by revoking direct EXECUTE from `PUBLIC`, `anon`, `authenticated`, and `service_role`, while leaving `ensure_rls` enabled. This exact behavior passed isolated PostgreSQL 16 CI before it was applied. The live catalog confirms only the function owner retains EXECUTE.

The project also retains default grants for `anon`, `authenticated`, and `service_role` on public tables, functions, and sequences. Prepare a separate, reviewed default-privilege hardening plan for both `postgres` and `supabase_admin` before creating application objects. Keep application data access on the trusted backend database connection unless a separate, intentionally designed Data API/RLS model is approved.

## Actions completed and deliberately not performed

- Applied the reviewed initial schema baseline: 22 tables, 23 indexes, RLS enabled on every table; all tables remain empty.
- Revoked direct API execution of `public.rls_auto_enable()` while preserving the enabled `ensure_rls` event trigger.
- Re-ran Supabase security and health advisors; the public-function execution warnings are gone. The remaining 22 RLS-without-policy notices are informational and intentional for a backend-only connection model; do not enable browser Data API access without a separate policy design.
- Merged PR #102 and deployed the autonomous learning-cycle changes to Railway; production health is online.
- Did not change Railway environment variables, migrate the existing SQLite volume, import data, or switch the live application database. The Railway variable values are redacted by the connected integration, so the Supabase runtime connection still requires the owner-only dashboard test.
