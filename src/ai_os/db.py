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
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memory_entries (
            id TEXT PRIMARY KEY, key TEXT NOT NULL, content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY, event_type TEXT NOT NULL, actor_id TEXT NOT NULL,
            entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        );
        """)
        # Backward-compatible migration for databases created before agent assignment.
        task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
        }
        if "assigned_agent" not in task_columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN assigned_agent TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks(status, created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_key ON memory_entries(key)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at)"
        )
