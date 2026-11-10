# Supabase migrations

AIOS now includes a source-derived PostgreSQL baseline migration:

`20261110160000_aios_initial_schema.sql`

## Validation status

The baseline passed isolated PostgreSQL 16 CI validation in GitHub Actions run
[#42781234481](https://github.com/hamza00alik-source/ai-operating-system/actions/runs/42781234481).
The test applied it to a disposable CI database and verified 22 public tables,
23 named indexes, RLS enabled on all 22 tables, and compatibility with the
application database initializer and selected runtime queries.

This is not a live Supabase migration test. The connected Supabase project has
not had this migration applied. Its Supabase-specific RLS event trigger behavior
and the Railway-to-Supabase runtime connection still need separate validation.

## Production safety

Do not run `supabase db push` or apply this SQL to the connected project until
the baseline has been reviewed against the live schema, a verified backup and
rollback plan exist, and the owner has explicitly approved the production change.

## Rules

- Use timestamped files: `YYYYMMDDHHMMSS_description.sql`.
- Keep schema changes additive where possible and include rollback notes in the PR.
- Never put passwords, service-role keys, access tokens, or customer data in migrations.
- Review generated SQL before applying it.
- Production migration execution requires separate owner approval and a verified backup.
