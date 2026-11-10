# Supabase integration

AIOS uses PostgreSQL through the existing `AI_OS_DATABASE_URL` setting. Supabase is
a PostgreSQL provider; connecting the Supabase project to GitHub for migration
versioning is separate from connecting the Railway runtime to the live database.

## Required Railway setting

Set `AI_OS_DATABASE_URL` in the Railway service environment to the Supabase
PostgreSQL connection string. Prefer Supabase's **Session pooler** connection when
the runtime has IPv4-only egress. Use the pooler host and port shown by Supabase
Connect; keep SSL enabled (`sslmode=require`). Do not paste the connection string
into chat, source files, logs, issues, or commits.

Optional `SUPABASE_URL` may be set to the project HTTPS URL for future Supabase
REST/Auth/Storage adapters. This first integration does not need an anon key or
service-role key and does not request either.

## Owner-only diagnostics

- `GET /integrations/supabase/status` reports whether a PostgreSQL target and
  optional project URL are configured. It never returns environment values.
- `POST /integrations/supabase/test` performs a five-second, TLS-required
  `SELECT 1` connectivity probe. It does not write data or alter schema.
- Both routes require owner authentication.

The diagnostic can identify a Supabase database host from the configured hostname.
A GitHub repository link alone does not prove the Railway database URL is configured
or reachable.

## Migrations and safety

`supabase/migrations/` is prepared for reviewed, timestamped SQL migrations.
It currently contains no baseline schema migration. AIOS's current schema is also
initialized by application code, so do not apply an incomplete migration history
to a live database. First compare the complete AIOS schema with the live Supabase
schema, create and review a baseline, take a verified backup, and obtain owner
approval. This implementation intentionally does not run `db push`, create tables,
drop objects, import data, or switch production databases.
