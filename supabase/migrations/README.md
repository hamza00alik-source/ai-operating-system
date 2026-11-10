# Supabase migrations

This directory is reserved for version-controlled Supabase CLI migrations.

## Current state

The AIOS application has a PostgreSQL adapter, but its existing schema is currently
created and upgraded by the application initializer. A complete baseline migration
has **not** yet been generated or reconciled against the live Supabase database.
Do not run `supabase db push` or apply SQL from this directory until that baseline
has been reviewed against a backup and explicitly approved by the owner.

## Rules

- Use timestamped files: `YYYYMMDDHHMMSS_description.sql`.
- Keep schema changes additive where possible and include rollback notes in the PR.
- Never put passwords, service-role keys, access tokens, or customer data in migrations.
- Review generated SQL before applying it.
- Production migration execution requires a separate owner approval and a verified backup.
