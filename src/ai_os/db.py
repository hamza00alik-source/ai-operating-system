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
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_title TEXT NOT NULL,
            source_published_at TEXT,
            source_accessed_at TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
            tags_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL CHECK(status IN ('candidate','accepted','rejected')),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            review_note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_status_category
            ON knowledge_items(status, category, created_at);
        CREATE TABLE IF NOT EXISTS consumed_agent_nonces (
            nonce TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_consumed_agent_nonces_expiry
            ON consumed_agent_nonces(expires_at);
        CREATE TABLE IF NOT EXISTS owner_approval_requests (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            action_type TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            action_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','consumed','expired')),
            created_at TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            decided_at TEXT,
            decision TEXT,
            consumed_at TEXT,
            execution_id TEXT UNIQUE
        );
        CREATE INDEX IF NOT EXISTS idx_owner_approval_status_expiry
            ON owner_approval_requests(status, expires_at);
        CREATE TABLE IF NOT EXISTS agent_evaluations (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_key TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            evaluator_version TEXT NOT NULL,
            score INTEGER NOT NULL CHECK(score >= 0 AND score <= 100),
            passed INTEGER NOT NULL CHECK(passed IN (0,1)),
            critical_failures_json TEXT NOT NULL,
            checks_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id, step_key) REFERENCES company_run_steps(run_id, step_key)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_agent_evaluations_agent_created
            ON agent_evaluations(agent_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_evaluations_run_created
            ON agent_evaluations(run_id, created_at);
        CREATE TABLE IF NOT EXISTS improvement_proposals (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            title TEXT NOT NULL,
            problem TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            proposed_change TEXT NOT NULL,
            expected_impact TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('candidate','approved_for_testing','rejected')),
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            review_note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_improvement_proposals_status_created
            ON improvement_proposals(status, created_at);
        CREATE TABLE IF NOT EXISTS improvement_test_runs (
            id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            screening_policy_version TEXT NOT NULL,
            candidate_sha256 TEXT NOT NULL,
            passed INTEGER NOT NULL CHECK(passed IN (0,1)),
            checks_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(proposal_id) REFERENCES improvement_proposals(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_improvement_test_runs_proposal_created
            ON improvement_test_runs(proposal_id, created_at);
        """)
