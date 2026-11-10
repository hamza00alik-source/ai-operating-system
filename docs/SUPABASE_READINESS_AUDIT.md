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

The app's current schema is created and incrementally upgraded by `src/ai_os/db.py` and additional feature modules. It is not yet represented by a complete, reviewed Supabase baseline migration. Do not point the live Railway service at this empty database until the full schema and all runtime-created tables have been inventoried, a migration baseline has been generated and reviewed, and a backup/rollback plan exists.

## Security recommendation

A separate draft migration restricts direct execution of `public.rls_auto_enable()` by `PUBLIC`, `anon`, and `authenticated`. It does not disable the `ensure_rls` event trigger. Review this migration before applying it.

## Actions deliberately not performed

- No tables, policies, functions, triggers, or migrations were created or changed in Supabase.
- No production Railway variables were changed.
- No data was imported or migrated.
- No production database switch or deployment was triggered.
