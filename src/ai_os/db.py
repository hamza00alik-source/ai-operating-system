"""SQLite persistence layer and additive schema migrations."""
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
    connection = sqlite3.connect(
        _database_path(), check_same_thread=False, timeout=15
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 15000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_column(connection: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    existing = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if name not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def initialize_database() -> None:
    """Create base tables and apply backward-compatible task-worker migrations."""
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
        """)
        _ensure_column(connection, "tasks", "result", "TEXT")
        _ensure_column(connection, "tasks", "error", "TEXT")
        _ensure_column(connection, "tasks", "worker_id", "TEXT")
        _ensure_column(connection, "tasks", "lease_expires_at", "TEXT")
        _ensure_column(connection, "tasks", "attempts", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "tasks", "max_attempts", "INTEGER NOT NULL DEFAULT 3")
        _ensure_column(connection, "tasks", "started_at", "TEXT")
        _ensure_column(connection, "tasks", "completed_at", "TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks(status, created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_lease ON tasks(status, lease_expires_at)"
        )
