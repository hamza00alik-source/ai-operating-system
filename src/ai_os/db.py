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
        """)
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS agent_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            step_key TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            prompt TEXT NOT NULL,
            output TEXT,
            error TEXT,
            worker_id TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            UNIQUE(task_id, step_key),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            source_agent TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, memory_key),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        """)
        # Additive migrations keep existing SQLite installations compatible.
        task_columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)")}
        approval_columns = {row["name"] for row in connection.execute("PRAGMA table_info(approvals)")}
        for name, sql_type in (
            ("actor_id", "TEXT"),
            ("resource_id", "TEXT"),
            ("action_payload_json", "TEXT"),
            ("action_fingerprint", "TEXT"),
            ("expires_at", "TEXT"),
            ("consumed_at", "TEXT"),
        ):
            if name not in approval_columns:
                connection.execute(f"ALTER TABLE approvals ADD COLUMN {name} {sql_type}")

        for name, sql_type in (
            ("worker_id", "TEXT"),
            ("started_at", "TEXT"),
            ("finished_at", "TEXT"),
            ("result", "TEXT"),
            ("error", "TEXT"),
            ("lease_expires_at", "TEXT"),
        ):
            if name not in task_columns:
                connection.execute(f"ALTER TABLE tasks ADD COLUMN {name} {sql_type}")

