"""SQLite persistence layer."""
import sqlite3
from pathlib import Path

from ai_os.config import get_settings


def _database_path() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("This starter currently supports SQLite URLs only.")
    path = url.removeprefix("sqlite:///")
    if path == ":memory:":
        return path
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return str(database_path)


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            department TEXT NOT NULL DEFAULT 'general',
            status TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY, task_id TEXT, action TEXT NOT NULL,
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
            status_json TEXT NOT NULL DEFAULT '{}', source_url TEXT NOT NULL,
            synced_at TEXT NOT NULL, review_state TEXT NOT NULL DEFAULT 'pending',
            PRIMARY KEY(source_id, provider_id)
        );
        CREATE INDEX IF NOT EXISTS idx_provider_catalog_category ON provider_catalog_entries(category, name);
        CREATE TABLE IF NOT EXISTS provider_credentials (
            provider TEXT PRIMARY KEY, encrypted_secret TEXT NOT NULL,
            model TEXT NOT NULL, base_url TEXT NOT NULL,
            free_confirmed INTEGER NOT NULL DEFAULT 0
        );
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
            id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, department TEXT NOT NULL DEFAULT 'general',
            task_title TEXT NOT NULL, outcome TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_brain_experiences_department ON brain_experiences(department, created_at);
        CREATE TABLE IF NOT EXISTS brain_memories (
            id TEXT PRIMARY KEY, category TEXT NOT NULL DEFAULT 'lesson',
            department TEXT NOT NULL DEFAULT 'general', title TEXT NOT NULL,
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
