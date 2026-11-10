"""SQLite and PostgreSQL persistence adapters."""
import re
import sqlite3
from pathlib import Path

from ai_os.config import get_settings


def _database_path() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("A SQLite URL is required for the SQLite adapter.")
    path = url.removeprefix("sqlite:///")
    if path == ":memory:":
        return path
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return str(database_path)


def _postgres_sql(statement: str) -> str | tuple[str, tuple[str, ...]]:
    """Translate the SQLite-specific SQL used by the existing persistence layer."""
    pragma = re.fullmatch(r"\s*PRAGMA\s+table_info\((\w+)\)\s*;?\s*", statement, re.IGNORECASE)
    if pragma:
        table = pragma.group(1).lower()
        return (
            'SELECT (c.ordinal_position - 1) AS cid, c.column_name AS name, '
            'upper(c.data_type) AS type, '
            "CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS \"notnull\", "
            'c.column_default AS dflt_value, '
            'CASE WHEN pk.column_name IS NOT NULL THEN 1 ELSE 0 END AS pk '
            'FROM information_schema.columns AS c '
            'LEFT JOIN ('
            'SELECT kcu.column_name FROM information_schema.table_constraints AS tc '
            'JOIN information_schema.key_column_usage AS kcu '
            'ON tc.constraint_name = kcu.constraint_name '
            'AND tc.table_schema = kcu.table_schema '
            'AND tc.table_name = kcu.table_name '
            "WHERE tc.constraint_type = 'PRIMARY KEY' "
            'AND tc.table_schema = current_schema() AND tc.table_name = %s'
            ') AS pk ON pk.column_name = c.column_name '
            'WHERE c.table_schema = current_schema() AND c.table_name = %s '
            'ORDER BY c.ordinal_position',
            (table, table),
        )
    statement = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "BIGSERIAL PRIMARY KEY",
        statement,
        flags=re.IGNORECASE,
    )
    return statement.replace("?", "%s")


class _PostgresConnection:
    """Expose the sqlite-style execute/executescript interface over psycopg."""
    def __init__(self, connection):
        self._connection = connection

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._connection.__exit__(exc_type, exc, traceback)

    def execute(self, statement, parameters=()):
        translated = _postgres_sql(statement)
        if isinstance(translated, tuple):
            statement, fixed_parameters = translated
            parameters = fixed_parameters
        else:
            statement = translated
        return self._connection.execute(statement, parameters)

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)
        return self

    def close(self):
        return self._connection.close()


def connect():
    url = get_settings().database_url
    if url.startswith("sqlite:///"):
        connection = sqlite3.connect(_database_path(), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection
    if url.startswith(("postgres://", "postgresql://")):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg[binary]. Install project dependencies."
            ) from exc
        return _PostgresConnection(psycopg.connect(url, row_factory=dict_row))
    raise ValueError("AI_OS_DATABASE_URL must use sqlite:/// or postgresql://.")


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            department TEXT NOT NULL DEFAULT 'general',
            business_id TEXT NOT NULL DEFAULT 'core',
            status TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY, task_id TEXT, business_id TEXT NOT NULL DEFAULT 'core', action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, decided_at TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS discovery_scans (
            id TEXT PRIMARY KEY, categories TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
            result_count INTEGER NOT NULL DEFAULT 0, error TEXT
        );
        CREATE TABLE IF NOT EXISTS provider_catalog_entries (
            source_id TEXT NOT NULL, provider_id TEXT NOT NULL,
            name TEXT NOT NULL, category TEXT NOT NULL,
            website TEXT NOT NULL DEFAULT '', api_key_url TEXT NOT NULL DEFAULT '',
            base_url TEXT NOT NULL DEFAULT '', free_tier_json TEXT NOT NULL DEFAULT '{}',
            policy_json TEXT NOT NULL DEFAULT '{}', confidence TEXT NOT NULL DEFAULT 'unknown',
            last_verified TEXT, probe_json TEXT NOT NULL DEFAULT '{}',
            status_json TEXT NOT NULL DEFAULT '{}', sources_json TEXT NOT NULL DEFAULT '[]', source_url TEXT NOT NULL,
            synced_at TEXT NOT NULL, review_state TEXT NOT NULL DEFAULT 'pending',
            PRIMARY KEY(source_id, provider_id)
        );
        CREATE INDEX IF NOT EXISTS idx_provider_catalog_category ON provider_catalog_entries(category, name);
        CREATE TABLE IF NOT EXISTS research_sources (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL DEFAULT 'core', url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL, captured_at TEXT NOT NULL, content_type TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_research_sources_captured ON research_sources(captured_at);
        CREATE TABLE IF NOT EXISTS provider_credentials (
            provider TEXT PRIMARY KEY, encrypted_secret TEXT NOT NULL,
            model TEXT NOT NULL, base_url TEXT NOT NULL,
            free_confirmed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS business_integration_credentials (
            business_id TEXT NOT NULL, provider TEXT NOT NULL,
            encrypted_secret TEXT NOT NULL, config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(business_id, provider)
        );
        CREATE INDEX IF NOT EXISTS idx_business_integrations_scope ON business_integration_credentials(business_id, provider);
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            assigned_agent_id TEXT,
            specialist_output TEXT,
            ceo_review TEXT,
            usage_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created ON agent_runs(status, created_at);
        CREATE TABLE IF NOT EXISTS agent_run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES agent_runs(id)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_run_id ON agent_run_events(run_id, id);
        CREATE TABLE IF NOT EXISTS agent_run_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            role TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            input_summary TEXT NOT NULL DEFAULT '',
            output TEXT NOT NULL DEFAULT '',
            error TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            FOREIGN KEY(run_id) REFERENCES agent_runs(id),
            UNIQUE(run_id, sequence_no)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run_id ON agent_run_steps(run_id, sequence_no);
        CREATE TABLE IF NOT EXISTS brain_experiences (
            id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, business_id TEXT NOT NULL DEFAULT 'core',
            department TEXT NOT NULL DEFAULT 'general', task_title TEXT NOT NULL, outcome TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_brain_experiences_department ON brain_experiences(department, created_at);
        CREATE TABLE IF NOT EXISTS brain_memories (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL DEFAULT 'core',
            category TEXT NOT NULL DEFAULT 'lesson', department TEXT NOT NULL DEFAULT 'general', title TEXT NOT NULL,
            content TEXT NOT NULL, source_run_id TEXT, status TEXT NOT NULL DEFAULT 'proposed',
            confidence REAL NOT NULL DEFAULT 0.5, created_at TEXT NOT NULL,
            reviewed_at TEXT, review_note TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_brain_memories_status_department ON brain_memories(status, department, created_at);
        CREATE TABLE IF NOT EXISTS owner_sessions (
            token_hash TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS business_records (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL DEFAULT 'core', record_type TEXT NOT NULL CHECK(record_type IN ('customer','expense','revenue')),
            title TEXT NOT NULL, amount REAL, currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
            approval_id TEXT, contact TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_business_records_type_created ON business_records(record_type, created_at);
        CREATE TABLE IF NOT EXISTS investor_contacts (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL DEFAULT 'core', name TEXT NOT NULL, organization TEXT NOT NULL DEFAULT '',
            contact TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT 'prospect',
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_investor_contacts_stage ON investor_contacts(stage, created_at);
        CREATE TABLE IF NOT EXISTS code_assets (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, repository_url TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL DEFAULT '', asset_type TEXT NOT NULL DEFAULT 'source_code',
            ownership_status TEXT NOT NULL DEFAULT 'unverified', license TEXT NOT NULL DEFAULT 'unknown',
            dependency_review TEXT NOT NULL DEFAULT 'not_reviewed', token_estimate INTEGER,
            token_method TEXT NOT NULL DEFAULT 'not_measured', git_history_tokens INTEGER,
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_code_assets_created ON code_assets(created_at);
        CREATE TABLE IF NOT EXISTS license_offers (
            id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, buyer TEXT NOT NULL,
            terms TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft_pending_owner_approval',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(asset_id) REFERENCES code_assets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_license_offers_created ON license_offers(created_at);
        CREATE TABLE IF NOT EXISTS department_messages (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL, sender_department TEXT NOT NULL,
            recipient_department TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
            related_task_id TEXT, status TEXT NOT NULL DEFAULT 'unread',
            created_at TEXT NOT NULL, read_at TEXT,
            FOREIGN KEY(related_task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_department_messages_inbox
            ON department_messages(business_id, recipient_department, status, created_at);
        CREATE INDEX IF NOT EXISTS idx_department_messages_thread
            ON department_messages(business_id, created_at);
        CREATE TABLE IF NOT EXISTS department_delegations (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL, parent_task_id TEXT,
            child_task_id TEXT NOT NULL UNIQUE, from_department TEXT NOT NULL,
            to_department TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT NOT NULL,
            FOREIGN KEY(parent_task_id) REFERENCES tasks(id),
            FOREIGN KEY(child_task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_department_delegations_scope
            ON department_delegations(business_id, status, created_at);
        CREATE TABLE IF NOT EXISTS discovery_candidates (
            canonical_url TEXT PRIMARY KEY, full_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL,
            license TEXT NOT NULL DEFAULT 'unknown',
            maintenance TEXT NOT NULL DEFAULT 'unknown',
            status TEXT NOT NULL, stars INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT NOT NULL, evidence TEXT NOT NULL,
            review_state TEXT NOT NULL DEFAULT 'pending',
            review_notes TEXT NOT NULL DEFAULT '',
            review_updated_at TEXT
        );
        """)
        # Backward-compatible migration for databases created before agent-run
        # task linkage. CREATE TABLE IF NOT EXISTS does not alter an existing
        # SQLite table, so older persistent volumes need an explicit migration.
        agent_run_columns = {row["name"] for row in connection.execute("PRAGMA table_info(agent_runs)")}
        if "task_id" not in agent_run_columns:
            connection.execute("ALTER TABLE agent_runs ADD COLUMN task_id TEXT")
        # Older persistent databases predate the collaborative worker fields.
        # Add every column written by the current runtime before it claims a run.
        agent_run_migrations = {
            "assigned_agent_id": "TEXT",
            "specialist_output": "TEXT",
            "ceo_review": "TEXT",
            "usage_json": "TEXT",
            "error": "TEXT",
            "started_at": "TEXT",
            "finished_at": "TEXT",
        }
        for column_name, column_type in agent_run_migrations.items():
            if column_name not in agent_run_columns:
                connection.execute(
                    "ALTER TABLE agent_runs ADD COLUMN " + column_name + " " + column_type
                )
        # Backward-compatible migration for databases created before owner review.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(discovery_candidates)")}
        if "review_state" not in columns:
            connection.execute("ALTER TABLE discovery_candidates ADD COLUMN review_state TEXT NOT NULL DEFAULT 'pending'")
        if "review_notes" not in columns:
            connection.execute("ALTER TABLE discovery_candidates ADD COLUMN review_notes TEXT NOT NULL DEFAULT ''")
        if "review_updated_at" not in columns:
            connection.execute("ALTER TABLE discovery_candidates ADD COLUMN review_updated_at TEXT")
        # Add explicit business ownership to operational records. Legacy rows remain in core.
        for table_name in ("approvals", "business_records", "investor_contacts", "research_sources"):
            scoped_columns = {row["name"] for row in connection.execute("PRAGMA table_info(" + table_name + ")")}
            if "business_id" not in scoped_columns:
                connection.execute("ALTER TABLE " + table_name + " ADD COLUMN business_id TEXT NOT NULL DEFAULT 'core'")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_business_records_scope ON business_records(business_id, record_type, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_investor_contacts_scope ON investor_contacts(business_id, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_sources_scope ON research_sources(business_id, captured_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_approvals_scope ON approvals(business_id, status, created_at)")
        business_columns = {row["name"] for row in connection.execute("PRAGMA table_info(business_records)")}
        if "approval_id" not in business_columns:
            connection.execute("ALTER TABLE business_records ADD COLUMN approval_id TEXT")
        # Existing tasks and memories remain in core; never copy legacy knowledge into business brains.
        for table_name in ("tasks", "brain_experiences", "brain_memories"):
            table_columns = {row["name"] for row in connection.execute("PRAGMA table_info(" + table_name + ")")}
            if "business_id" not in table_columns:
                connection.execute("ALTER TABLE " + table_name + " ADD COLUMN business_id TEXT NOT NULL DEFAULT 'core'")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_brain_memories_business_status ON brain_memories(business_id, status, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_brain_experiences_business ON brain_experiences(business_id, created_at)")
        provider_columns = {row["name"] for row in connection.execute("PRAGMA table_info(provider_catalog_entries)")}
        if "sources_json" not in provider_columns:
            connection.execute("ALTER TABLE provider_catalog_entries ADD COLUMN sources_json TEXT NOT NULL DEFAULT '[]'")
