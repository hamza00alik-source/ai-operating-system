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
| `tasks` | id TEXT*; title TEXT*; description TEXT* DEFAULT ''; department TEXT* DEFAULT 'general'; business_id TEXT* DEFAULT 'core'; status TEXT* DEFAULT 'queued'; created_at TEXT* | PK(id) |
| `approvals` | id TEXT*; task_id TEXT; business_id TEXT* DEFAULT 'core'; action TEXT*; details TEXT* DEFAULT ''; status TEXT* DEFAULT 'pending'; created_at TEXT*; decided_at TEXT | PK(id); FK(task_id) → tasks(id) |
| `discovery_scans` | id TEXT*; categories TEXT*; status TEXT*; created_at TEXT*; started_at TEXT; finished_at TEXT; result_count INTEGER* DEFAULT 0; error TEXT | PK(id) |
| `provider_catalog_entries` | source_id TEXT*; provider_id TEXT*; name TEXT*; category TEXT*; website TEXT* DEFAULT ''; api_key_url TEXT* DEFAULT ''; base_url TEXT* DEFAULT ''; free_tier_json TEXT* DEFAULT '{}'; policy_json TEXT* DEFAULT '{}'; confidence TEXT* DEFAULT 'unknown'; last_verified TEXT; probe_json TEXT* DEFAULT '{}'; status_json TEXT* DEFAULT '{}'; sources_json TEXT* DEFAULT '[]'; source_url TEXT*; synced_at TEXT*; review_state TEXT* DEFAULT 'pending' | Composite PK(source_id, provider_id) |
| `research_sources` | id TEXT*; business_id TEXT* DEFAULT 'core'; url TEXT*; title TEXT* DEFAULT ''; content TEXT*; captured_at TEXT*; content_type TEXT* DEFAULT '' | PK(id) |
| `provider_credentials` | provider TEXT*; encrypted_secret TEXT*; model TEXT*; base_url TEXT*; free_confirmed INTEGER* DEFAULT 0 | PK(provider) |
| `business_integration_credentials` | business_id TEXT*; provider TEXT*; encrypted_secret TEXT*; config_json TEXT* DEFAULT '{}'; created_at TEXT*; updated_at TEXT* | Composite PK(business_id, provider) |
| `agent_runs` | id TEXT*; task_id TEXT*; status TEXT* DEFAULT 'queued'; assigned_agent_id TEXT; specialist_output TEXT; ceo_review TEXT; usage_json TEXT; error TEXT; created_at TEXT*; started_at TEXT; finished_at TEXT | PK(id); FK(task_id) → tasks(id) |
| `agent_run_events` | id INTEGER* AUTOINCREMENT; run_id TEXT*; stage TEXT*; message TEXT*; created_at TEXT* | PK(id); FK(run_id) → agent_runs(id) |
| `agent_run_steps` | id INTEGER* AUTOINCREMENT; run_id TEXT*; sequence_no INTEGER*; role TEXT*; agent_id TEXT*; agent_name TEXT*; status TEXT* DEFAULT 'running'; input_summary TEXT* DEFAULT ''; output TEXT* DEFAULT ''; error TEXT; created_at TEXT*; finished_at TEXT | PK(id); FK(run_id) → agent_runs(id); UNIQUE(run_id, sequence_no) |
| `brain_experiences` | id TEXT*; run_id TEXT; task_id TEXT; business_id TEXT* DEFAULT 'core'; department TEXT* DEFAULT 'general'; task_title TEXT*; outcome TEXT*; created_at TEXT* | PK(id) |
| `brain_memories` | id TEXT*; business_id TEXT* DEFAULT 'core'; category TEXT* DEFAULT 'lesson'; department TEXT* DEFAULT 'general'; title TEXT*; content TEXT*; source_run_id TEXT; status TEXT* DEFAULT 'proposed'; confidence REAL* DEFAULT 0.5; created_at TEXT*; reviewed_at TEXT; review_note TEXT* DEFAULT '' | PK(id) |
| `owner_sessions` | token_hash TEXT*; created_at TEXT*; expires_at TEXT*; last_seen_at TEXT* | PK(token_hash) |
| `business_records` | id TEXT*; business_id TEXT* DEFAULT 'core'; record_type TEXT* CHECK IN ('customer','expense','revenue'); title TEXT*; amount REAL; currency TEXT* DEFAULT 'USD'; status TEXT*; verified INTEGER* DEFAULT 0; approval_id TEXT; contact TEXT* DEFAULT ''; notes TEXT* DEFAULT ''; created_at TEXT* | PK(id); CHECK(record_type); approval_id is not declared as an FK in source |
| `investor_contacts` | id TEXT*; business_id TEXT* DEFAULT 'core'; name TEXT*; organization TEXT* DEFAULT ''; contact TEXT* DEFAULT ''; stage TEXT* DEFAULT 'prospect'; notes TEXT* DEFAULT ''; created_at TEXT*; updated_at TEXT* | PK(id) |
| `code_assets` | id TEXT*; name TEXT*; repository_url TEXT* DEFAULT ''; path TEXT* DEFAULT ''; asset_type TEXT* DEFAULT 'source_code'; ownership_status TEXT* DEFAULT 'unverified'; license TEXT* DEFAULT 'unknown'; dependency_review TEXT* DEFAULT 'not_reviewed'; token_estimate INTEGER; token_method TEXT* DEFAULT 'not_measured'; git_history_tokens INTEGER; notes TEXT* DEFAULT ''; created_at TEXT*; updated_at TEXT* | PK(id) |
| `license_offers` | id TEXT*; asset_id TEXT*; buyer TEXT*; terms TEXT*; status TEXT* DEFAULT 'draft_pending_owner_approval'; created_at TEXT*; updated_at TEXT* | PK(id); FK(asset_id) → code_assets(id) |
| `department_messages` | id TEXT*; business_id TEXT*; sender_department TEXT*; recipient_department TEXT*; subject TEXT*; body TEXT*; related_task_id TEXT; status TEXT* DEFAULT 'unread'; created_at TEXT*; read_at TEXT | PK(id); FK(related_task_id) → tasks(id) |
| `department_delegations` | id TEXT*; business_id TEXT*; parent_task_id TEXT; child_task_id TEXT* UNIQUE; from_department TEXT*; to_department TEXT*; title TEXT*; status TEXT* DEFAULT 'queued'; created_at TEXT* | PK(id); UNIQUE(child_task_id); FK(parent_task_id) → tasks(id); FK(child_task_id) → tasks(id) |
| `discovery_candidates` | canonical_url TEXT*; full_name TEXT*; description TEXT* DEFAULT ''; category TEXT*; license TEXT* DEFAULT 'unknown'; maintenance TEXT* DEFAULT 'unknown'; status TEXT*; stars INTEGER* DEFAULT 0; discovered_at TEXT*; evidence TEXT*; review_state TEXT* DEFAULT 'pending'; review_notes TEXT* DEFAULT ''; review_updated_at TEXT | PK(canonical_url) |

### Workflow tables (2)

| Table | Columns (type; NOT NULL marked *) | Keys and constraints |
|---|---|---|
| `workflow_instances` | id TEXT*; business_id TEXT* DEFAULT 'core'; template_id TEXT*; name TEXT*; status TEXT* DEFAULT 'active'; created_at TEXT* | PK(id) |
| `workflow_steps` | id TEXT*; workflow_id TEXT*; task_id TEXT*; sequence_no INTEGER*; department TEXT*; title TEXT*; status TEXT* DEFAULT 'blocked'; output TEXT* DEFAULT ''; dependencies_json TEXT* DEFAULT '[]'; created_at TEXT* | PK(id); UNIQUE(workflow_id, sequence_no); UNIQUE(task_id); FK(workflow_id) → workflow_instances(id); FK(task_id) → tasks(id) |

## Index inventory (23)

| Index | Table | Indexed columns |
|---|---|---|
| idx_provider_catalog_category | provider_catalog_entries | category, name |
| idx_research_sources_captured | research_sources | captured_at |
| idx_business_integrations_scope | business_integration_credentials | business_id, provider |
| idx_agent_runs_status_created | agent_runs | status, created_at |
| idx_agent_run_events_run_id | agent_run_events | run_id, id |
| idx_agent_run_steps_run_id | agent_run_steps | run_id, sequence_no |
| idx_brain_experiences_department | brain_experiences | department, created_at |
| idx_brain_memories_status_department | brain_memories | status, department, created_at |
| idx_business_records_type_created | business_records | record_type, created_at |
| idx_investor_contacts_stage | investor_contacts | stage, created_at |
| idx_code_assets_created | code_assets | created_at |
| idx_license_offers_created | license_offers | created_at |
| idx_department_messages_inbox | department_messages | business_id, recipient_department, status, created_at |
| idx_department_messages_thread | department_messages | business_id, created_at |
| idx_department_delegations_scope | department_delegations | business_id, status, created_at |
| idx_business_records_scope | business_records | business_id, record_type, created_at |
| idx_investor_contacts_scope | investor_contacts | business_id, created_at |
| idx_research_sources_scope | research_sources | business_id, captured_at |
| idx_approvals_scope | approvals | business_id, status, created_at |
| idx_brain_memories_business_status | brain_memories | business_id, status, created_at |
| idx_brain_experiences_business | brain_experiences | business_id, created_at |
| idx_workflow_steps_workflow | workflow_steps | workflow_id, sequence_no |
| idx_workflow_instances_scope | workflow_instances | business_id, created_at |

## Backward-compatible schema upgrades in source

The runtime performs conditional ALTER TABLE operations for older persistent databases:

- `agent_runs`: add `task_id`, `assigned_agent_id`, `specialist_output`, `ceo_review`, `usage_json`, `error`, `started_at`, `finished_at` when absent.
- `discovery_candidates`: add `review_state`, `review_notes`, `review_updated_at` when absent.
- `approvals`, `business_records`, `investor_contacts`, `research_sources`: add `business_id TEXT NOT NULL DEFAULT 'core'` when absent.
- `business_records`: add `approval_id TEXT` when absent.
- `tasks`, `brain_experiences`, `brain_memories`: add `business_id TEXT NOT NULL DEFAULT 'core'` when absent.
- `provider_catalog_entries`: add `sources_json TEXT NOT NULL DEFAULT '[]'` when absent.
- `workflow_instances`: add `business_id TEXT NOT NULL DEFAULT 'core'` when absent.
- `workflow_steps`: add `output TEXT NOT NULL DEFAULT ''` and `dependencies_json TEXT NOT NULL DEFAULT '[]'` when absent.

The compatibility code also creates the business-scope and workflow-scope indexes listed above. A clean baseline should represent the final schema directly; it should not replay these conditional legacy ALTERs on a fresh database. Existing SQLite data migration is a separate migration concern.

## PostgreSQL/Supabase migration considerations

1. Preserve text-based timestamps and JSON payloads as TEXT in the first compatibility baseline. Do not silently convert to timestamptz/jsonb.
2. Preserve integer flags (`free_confirmed`, `verified`) as integers unless application code is deliberately changed.
3. Translate SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` to PostgreSQL identity or serial semantics, and verify returned IDs and sequence behavior through the existing psycopg adapter.
4. Reproduce all primary keys, composite keys, foreign keys, unique constraints, and the `business_records.record_type` CHECK constraint.
5. The app's PostgreSQL adapter rewrites `PRAGMA table_info`, `INSERT OR IGNORE`, autoincrement DDL, qmark placeholders, and now SQLite named placeholders (`:name`) to psycopg named placeholders (`%(name)s`). It is not a general SQLite-to-PostgreSQL SQL translator; all runtime SQL paths still need integration tests.
6. PostgreSQL enforces foreign keys; SQLite's default foreign-key enforcement is commonly disabled unless explicitly enabled. Test data creation and deletion paths with PostgreSQL semantics.
7. The app connects with a privileged database connection. Do not expose database credentials, service-role keys, or this connection to browser code. Do not grant Data API access merely to make the app work; the app uses its backend database adapter.
8. Supabase's project has an RLS auto-enable event trigger. The baseline explicitly enables RLS on all 22 application tables. Supabase-specific event-trigger behavior still needs validation on the actual project. Do not modify its function grants or event trigger as part of this migration without a separately reviewed remediation.
9. Keep schema migration execution separate from the production Railway database URL. The baseline was tested in an isolated PostgreSQL 16 CI service with synthetic data; it has not been run against the connected Supabase project.

## Known validation gaps

- The baseline migration passed isolated PostgreSQL 16 CI validation in GitHub Actions run #42781234481. The test verified 22 public tables, 23 named indexes, RLS enabled on all 22 tables, application initializer compatibility, table metadata inspection, named-parameter task insertion/selection, and discovery scan creation.
- No migration has been applied to the connected Supabase project.
- No end-to-end integration test against the actual Supabase project has been run.
- Runtime SQL outside the tested initialization/task/discovery paths still requires a full compatibility scan and test coverage.
- The 22-table inventory is based on the inspected source files; future runtime-created tables must be included if found in later source changes.

## Next safe step

Perform read-only Supabase-specific validation and safely test the Railway-to-Supabase connection without changing the production database target. Review the baseline and backup/rollback plan before seeking separate owner approval for any production migration.
