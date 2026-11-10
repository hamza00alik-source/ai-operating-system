# AIOS database schema inventory

Audit date: 2026-11-10  
Source branch inspected: `feature/owner-dashboard-account-connections-synced`  
Primary sources: `src/ai_os/db.py` and `src/ai_os/workflows.py`

## Scope and status

This is a source-derived inventory of the 22 application tables initialized by the current application. It is not a database dump. A corresponding standalone PostgreSQL baseline migration is now available at `supabase/migrations/20261110160000_aios_initial_schema.sql`. The 20 core tables are initialized by `initialize_database()`; two workflow tables are initialized by `initialize_workflows()`.

The baseline was applied to the connected Supabase project on 2026-11-10 after the project was verified empty. Post-application inspection confirms all 22 application tables exist, all have RLS enabled, and all have zero rows. Supabase records the baseline migration and a separate `rls_auto_enable()` function ACL remediation. The baseline also passed isolated PostgreSQL 16 CI validation (GitHub Actions run #42781234481). The live Railway application database has not been switched; verify the owner-only Railway-to-Supabase connection test and complete a SQLite backup/import/rollback plan before any switch.

## Table definitions

Column types below reflect the source DDL. `TEXT` JSON fields are deliberately retained as text: changing them to `jsonb` would require application changes and data conversion. Integer flags remain integers for compatibility.

### Core application tables (20)

| Table | Columns (type; NOT NULL marked *) | Keys and constraints |
|---|---|---|