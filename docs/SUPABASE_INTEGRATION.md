# Supabase integration

AIOS uses PostgreSQL through the existing `AI_OS_DATABASE_URL` setting. Supabase is
a PostgreSQL provider. Three separate connections must not be confused:

1. GitHub stores and reviews timestamped migration files.
2. Railway's AIOS runtime connects to the Supabase PostgreSQL database.
3. Supabase's Data API (REST/Auth/Storage) is optional and is not required by this
   server-side PostgreSQL integration.

## Railway runtime connection

Set `AI_OS_DATABASE_URL` on the `aios-api` service to the intended Supabase
PostgreSQL connection string only after the owner approves the production switch.
For an IPv4-only Railway runtime, use Supabase's Shared Pooler **Session mode**
(host `aws-[region].pooler.supabase.com`, port `5432`) and retain TLS
(`sslmode=require`). Session mode is appropriate for a persistent backend.
Transaction mode uses port `6543` and is intended for short-lived/serverless
clients; it has different session semantics.

Never paste the connection string into chat, source files, logs, issues, or commits.
The Railway connector currently redacts variable values, so the presence of
`AI_OS_DATABASE_URL` does not prove it points to this Supabase project.

Optional `SUPABASE_URL` may be set for future REST/Auth/Storage adapters. This
PostgreSQL integration does not require an anon key or service-role key.

## Owner-only diagnostics

- `GET /integrations/supabase/status` reports whether a PostgreSQL target and
  optional project URL are configured. It never returns environment values.
- `POST /integrations/supabase/test` performs a five-second, TLS-required
  `SELECT 1` connectivity probe. It does not write data or alter schema.
- Both routes require owner authentication and return sanitized connection errors.

A GitHub repository link or a Railway variable name alone does not prove that
the Railway runtime can connect to the intended Supabase project. The diagnostic
must be exercised from the deployed AIOS runtime after the PR is deliberately
deployed.

## Schema baseline and migration state

The source-derived baseline is
`supabase/migrations/20261110160000_aios_initial_schema.sql`. It creates
22 application tables and 23 named indexes, and enables RLS on all 22 tables.
It is designed for a new/empty AIOS database. It passed isolated PostgreSQL 16
CI validation, including application initializer compatibility and selected
runtime queries. This is not a live Supabase migration test.

The connected Supabase project was inspected read-only on 2026-11-10:
PostgreSQL 17.11, zero application tables, and zero recorded migrations.
No schema migration has been applied to that project.

## Supabase-specific security gates

The live project's security advisor reported that the internal
`public.rls_auto_enable()` SECURITY DEFINER function is executable through
the Data API by `PUBLIC`, `anon`, and `authenticated`. It is attached to the
`ensure_rls` DDL event trigger. Do not drop or disable that trigger. A narrowly
scoped function-EXECUTE ACL revocation is documented as a remediation candidate;
isolated PostgreSQL CI verified the event trigger continues to fire after direct
EXECUTE is revoked, but this remediation has **not** been applied to Supabase.

The project also has default grants for `anon`, `authenticated`, and
`service_role` on public tables, functions, and sequences for both
`postgres` and `supabase_admin`. Prepare and review a separate
default-privilege hardening plan before creating application objects. Keep
application data access on the trusted backend connection unless a separate
Data API/RLS access model is explicitly designed and approved.

## Production safety

Do not run `db push`, apply the baseline, change function ACLs/default
privileges, create application tables, import data, or switch Railway's live
database until all of the following are complete:

1. Review the full baseline and Supabase-specific security plan.
2. Verify a backup and a practical rollback/recovery plan.
3. Obtain explicit owner approval for each production action.
4. Apply one controlled change at a time and re-run Supabase advisors and
   application-level checks.

The PR intentionally does not run migrations, create/drop production objects,
change Supabase grants/functions/triggers, import data, or switch production
databases. The Railway production `aios-api` service remains on
`feature/owner-dashboard-account-connections-synced`; the Supabase integration
branch is not deployed.
