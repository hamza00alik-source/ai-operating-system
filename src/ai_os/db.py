"""SQLite persistence layer."""
import sqlite3
from pathlib import Path
from ai_os.config import get_settings

def _database_path() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("This starter currently supports SQLite URLs only.")
    path = url.removeprefix("sqlite:///")
    return path if path == ":memory:" else str(Path(path))

def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), check_same_thread=False, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
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
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            idempotency_key TEXT UNIQUE,
            result_json TEXT,
            error TEXT,
            locked_at TEXT,
            locked_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status_created
            ON jobs(status, created_at);
        CREATE TABLE IF NOT EXISTS company_runs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK(status IN ('queued','running','completed','blocked')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS company_run_steps (
            run_id TEXT NOT NULL,
            step_key TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            task TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            depends_on_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL CHECK(status IN ('pending','assigned','completed','blocked')),
            position INTEGER NOT NULL,
            work_packet_json TEXT,
            report_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(run_id, step_key),
            FOREIGN KEY(run_id) REFERENCES company_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_company_run_steps_status
            ON company_run_steps(run_id, status, position);
        CREATE TABLE IF NOT EXISTS ceo_plan_metadata (
            run_id TEXT PRIMARY KEY,
            objective TEXT NOT NULL,
            planning_mode TEXT NOT NULL,
            selected_workstreams_json TEXT NOT NULL,
            decision_log_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES company_runs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ceo_reviews (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, provider TEXT NOT NULL,
            model TEXT NOT NULL, review_json TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES company_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ceo_reviews_run_created ON ceo_reviews(run_id, created_at);
        CREATE TABLE IF NOT EXISTS audit_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            details_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_events(timestamp);
        CREATE TABLE IF NOT EXISTS consumed_agent_nonces (
            nonce TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_consumed_agent_nonces_expiry
            ON consumed_agent_nonces(expires_at);
        """)
