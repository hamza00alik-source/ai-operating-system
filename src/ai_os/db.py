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
        """)
