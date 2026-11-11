"""Local durable storage for the independent OpenCompany core.

SQLite is used as a small, inspectable persistence layer. All writes are
transactional; audit events are linked with SHA-256 hashes to make later
alteration detectable. This is tamper-evident, not a substitute for backups
or access controls.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from .domain import AgentProfile, AgentState, AuditRecord, TaskState, WorkItem


_ZERO_HASH = "0" * 64
_SCHEMA_VERSION = 5


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _audit_payload(record: AuditRecord, previous_hash: str) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "occurred_at": record.occurred_at.isoformat(),
        "actor_type": record.actor_type,
        "actor_id": record.actor_id,
        "action": record.action,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "outcome": record.outcome,
        "correlation_id": record.correlation_id,
        "details": dict(record.details),
        "previous_hash": previous_hash,
    }


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


class SQLiteStore:
    """Thread-safe repository for core records and append-only audit evidence."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        if self.database != ":memory:":
            parent = Path(self.database).expanduser().resolve().parent
            if not parent.exists():
                raise FileNotFoundError(f"database directory does not exist: {parent}")
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.database, timeout=10, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 10000")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise RuntimeError("database schema is newer than this application supports")
            if version == _SCHEMA_VERSION:
                return
            if version == 0:
                self._connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS agent_profiles (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        department TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        capabilities_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        role_key TEXT,
                        team_key TEXT
                    );
                    CREATE TABLE IF NOT EXISTS work_items (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        objective TEXT NOT NULL,
                        department TEXT NOT NULL,
                        business_id TEXT NOT NULL DEFAULT 'core',
                        state TEXT NOT NULL,
                        assigned_agent_id TEXT,
                        dependencies_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS audit_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        occurred_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL UNIQUE
                    );
                    CREATE INDEX IF NOT EXISTS idx_work_items_state_created
                        ON work_items(state, created_at);
                    CREATE TABLE IF NOT EXISTS deliverables (id TEXT PRIMARY KEY, work_item_id TEXT NOT NULL REFERENCES work_items(id), role_key TEXT NOT NULL, content TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, cost_usd REAL NOT NULL CHECK(cost_usd >= 0), created_at TEXT NOT NULL, review_required INTEGER NOT NULL CHECK(review_required IN (0,1)));
                    CREATE INDEX IF NOT EXISTS idx_deliverables_work_item ON deliverables(work_item_id, created_at);
                    PRAGMA user_version = 4;
                    COMMIT;
                """)
                return
            if version == 1:
                columns = {
                    row["name"] for row in self._connection.execute(
                        "PRAGMA table_info(agent_profiles)"
                    ).fetchall()
                }
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    if "role_key" not in columns:
                        self._connection.execute("ALTER TABLE agent_profiles ADD COLUMN role_key TEXT")
                    if "team_key" not in columns:
                        self._connection.execute("ALTER TABLE agent_profiles ADD COLUMN team_key TEXT")
                    self._connection.execute("PRAGMA user_version = 2")
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
                version = 2
            if version == 2:
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    self._connection.execute("CREATE TABLE IF NOT EXISTS deliverables (id TEXT PRIMARY KEY, work_item_id TEXT NOT NULL REFERENCES work_items(id), role_key TEXT NOT NULL, content TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, cost_usd REAL NOT NULL CHECK(cost_usd >= 0), created_at TEXT NOT NULL, review_required INTEGER NOT NULL CHECK(review_required IN (0,1)))")
                    self._connection.execute("CREATE INDEX IF NOT EXISTS idx_deliverables_work_item ON deliverables(work_item_id, created_at)")
                    self._connection.execute("PRAGMA user_version = 3")
                    self._connection.execute("COMMIT")
                    version = 3
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
            if version == 3:
                columns = {
                    row["name"] for row in self._connection.execute(
                        "PRAGMA table_info(work_items)"
                    ).fetchall()
                }
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    if "business_id" not in columns:
                        self._connection.execute(
                            "ALTER TABLE work_items ADD COLUMN business_id TEXT NOT NULL DEFAULT 'core'"
                        )
                    self._connection.execute("PRAGMA user_version = 4")
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
                return
            if version == 4:
                try:
                    self._connection.executescript("""
                        BEGIN IMMEDIATE;
                        CREATE TABLE IF NOT EXISTS commercial_opportunities (
                            id TEXT PRIMARY KEY,
                            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
                            customer_name TEXT NOT NULL,
                            customer_contact TEXT,
                            customer_need TEXT NOT NULL,
                            stage TEXT NOT NULL DEFAULT 'new' CHECK(stage IN ('new','qualified','proposal','won','lost','on_hold')),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_opportunities_unit
                            ON commercial_opportunities(business_id, created_at);
                        CREATE TABLE IF NOT EXISTS commercial_products (
                            id TEXT PRIMARY KEY,
                            business_id TEXT NOT NULL CHECK(business_id IN ('physical-agency','physical-brand','digital-products')),
                            name TEXT NOT NULL,
                            description TEXT NOT NULL,
                            category TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','archived')),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_commercial_products_unit
                            ON commercial_products(business_id, status, created_at);
                        PRAGMA user_version = 5;
                        COMMIT;
                    """)
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
                return
            raise RuntimeError(f"unsupported database schema version: {version}")


    def create_commercial_opportunity(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Create one customer opportunity scoped to exactly one commercial business."""
        allowed = {"physical-agency", "physical-brand", "digital-products"}
        if record.get("business_id") not in allowed:
            raise ValueError("opportunities must belong to one commercial business unit")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO commercial_opportunities
                       (id,business_id,customer_name,customer_contact,customer_need,stage,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (record["id"], record["business_id"], record["customer_name"],
                     record.get("customer_contact"), record["customer_need"],
                     record.get("stage", "new"), record["created_at"], record["updated_at"]),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(payload), previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def get_commercial_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM commercial_opportunities WHERE id=?", (opportunity_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_commercial_opportunities(
        self, *, business_id: str | None = None, limit: int = 500
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if business_id is not None and business_id not in {
            "physical-agency", "physical-brand", "digital-products"
        }:
            raise ValueError("unknown commercial business unit")
        sql = "SELECT * FROM commercial_opportunities"
        values: list[Any] = []
        if business_id is not None:
            sql += " WHERE business_id=?"
            values.append(business_id)
        sql += " ORDER BY created_at DESC,id LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(sql, tuple(values)).fetchall()
        return tuple(dict(row) for row in rows)

    def create_commercial_product(self, record: dict[str, Any], audit: AuditRecord) -> str:
        """Create a draft catalogue entry inside exactly one commercial unit."""
        allowed = {"physical-agency", "physical-brand", "digital-products"}
        if record.get("business_id") not in allowed:
            raise ValueError("catalogue products must belong to one commercial business unit")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO commercial_products
                       (id,business_id,name,description,category,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (record["id"], record["business_id"], record["name"],
                     record["description"], record["category"], record.get("status", "draft"),
                     record["created_at"], record["updated_at"]),
                )
                previous = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                payload = _audit_payload(audit, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    "INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)",
                    (str(audit.id), audit.occurred_at.isoformat(), _json(payload), previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def list_commercial_products(
        self, *, business_id: str | None = None, status: str | None = None, limit: int = 500
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if business_id is not None and business_id not in {
            "physical-agency", "physical-brand", "digital-products"
        }:
            raise ValueError("unknown commercial business unit")
        if status is not None and status not in {"draft", "active", "archived"}:
            raise ValueError("unknown catalogue status")
        clauses, values = [], []
        if business_id is not None:
            clauses.append("business_id=?")
            values.append(business_id)
        if status is not None:
            clauses.append("status=?")
            values.append(status)
        sql = "SELECT * FROM commercial_products"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC,id LIMIT ?"
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(sql, tuple(values)).fetchall()
        return tuple(dict(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def save_agent(self, agent: AgentProfile) -> None:
        with self._lock:
            self._connection.execute(
                """INSERT INTO agent_profiles
                   (id,name,department,purpose,capabilities_json,state,revision,role_key,team_key)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, department=excluded.department,
                     purpose=excluded.purpose, capabilities_json=excluded.capabilities_json,
                     state=excluded.state, revision=excluded.revision,
                     role_key=excluded.role_key, team_key=excluded.team_key""",
                (str(agent.id), agent.name, agent.department, agent.purpose,
                 _json(list(agent.capabilities)), agent.state.value, agent.revision,
                 agent.role_key, agent.team_key),
            )

    def list_agents(self, *, department: str | None = None, limit: int = 100) -> tuple[AgentProfile, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._lock:
            if department is None:
                rows = self._connection.execute(
                    "SELECT id FROM agent_profiles ORDER BY department,name,id LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT id FROM agent_profiles WHERE department=? ORDER BY name,id LIMIT ?",
                    (department, limit),
                ).fetchall()
        return tuple(self.get_agent(UUID(row["id"])) for row in rows)

    def save_agent_with_audit(self, agent: AgentProfile, record: AuditRecord) -> str | None:
        """Insert a new agent profile and its audit evidence atomically.

        Existing profiles are never overwritten by bootstrap retries.
        """
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    """INSERT OR IGNORE INTO agent_profiles
                       (id,name,department,purpose,capabilities_json,state,revision,role_key,team_key)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (str(agent.id), agent.name, agent.department, agent.purpose,
                     _json(list(agent.capabilities)), agent.state.value, agent.revision,
                     agent.role_key, agent.team_key),
                )
                if cursor.rowcount == 0:
                    self._connection.execute("ROLLBACK")
                    return None
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def update_agent_with_audit(
        self, agent: AgentProfile, record: AuditRecord, *, expected_revision: int
    ) -> bool:
        """Update an existing agent and append its audit event atomically."""
        if agent.revision != expected_revision + 1:
            raise ValueError("updated agent revision must increment exactly once")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute(
                    """UPDATE agent_profiles SET name=?,department=?,purpose=?,
                       capabilities_json=?,state=?,revision=?,role_key=?,team_key=?
                       WHERE id=? AND revision=?""",
                    (agent.name, agent.department, agent.purpose,
                     _json(list(agent.capabilities)), agent.state.value, agent.revision,
                     agent.role_key, agent.team_key, str(agent.id), expected_revision),
                )
                if cursor.rowcount != 1:
                    self._connection.execute("ROLLBACK")
                    return False
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def activate_all_draft_agents_with_audit(self) -> int:
        """Atomically activate all provisioned, catalogue-bound draft profiles."""
        correlation_id = str(uuid4())
        now = datetime.now(timezone.utc)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                rows = self._connection.execute(
                    """SELECT id,department,role_key,team_key,revision
                       FROM agent_profiles WHERE state=? ORDER BY department,role_key,id""",
                    (AgentState.DRAFT.value,),
                ).fetchall()
                for row in rows:
                    if not row["department"] or not row["role_key"] or not row["team_key"]:
                        raise ValueError("cannot activate a profile without department, role and team identity")
                    cursor = self._connection.execute(
                        """UPDATE agent_profiles SET state=?,revision=revision+1
                           WHERE id=? AND state=? AND revision=?""",
                        (AgentState.ACTIVE.value, row["id"], AgentState.DRAFT.value, row["revision"]),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("draft profile changed during workforce activation")
                    event = AuditRecord(
                        id=uuid4(), occurred_at=now, actor_type="owner",
                        actor_id="owner", action="agent.workforce_profile_activated",
                        subject_type="agent_profile", subject_id=row["id"],
                        outcome="active", correlation_id=correlation_id,
                        details={
                            "department": row["department"], "role_key": row["role_key"],
                            "team_key": row["team_key"], "activation_policy": "owner-approved-runtime-config",
                        },
                    )
                    previous = self._connection.execute(
                        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    previous_hash = previous["event_hash"] if previous else _ZERO_HASH
                    payload = _audit_payload(event, previous_hash)
                    self._connection.execute(
                        """INSERT INTO audit_events
                           (event_id,occurred_at,payload_json,previous_hash,event_hash)
                           VALUES(?,?,?,?,?)""",
                        (str(event.id), event.occurred_at.isoformat(), _json(payload),
                         previous_hash, _digest(payload)),
                    )
                self._connection.execute("COMMIT")
                return len(rows)
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def get_agent(self, agent_id: UUID) -> AgentProfile | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM agent_profiles WHERE id=?", (str(agent_id),)
            ).fetchone()
        if row is None:
            return None
        return AgentProfile(
            id=UUID(row["id"]), name=row["name"], department=row["department"],
            purpose=row["purpose"], capabilities=tuple(json.loads(row["capabilities_json"])),
            state=AgentState(row["state"]), revision=row["revision"],
            role_key=row["role_key"], team_key=row["team_key"],
        )

    def save_work_item(self, item: WorkItem) -> None:
        with self._lock:
            existing = self._connection.execute(
                "SELECT business_id FROM work_items WHERE id=?", (str(item.id),)
            ).fetchone()
            if existing is not None and existing["business_id"] != item.business_id:
                raise ValueError("a work item's business unit is immutable")
            self._connection.execute(
                """INSERT INTO work_items
                   (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, objective=excluded.objective,
                     department=excluded.department, state=excluded.state,
                     assigned_agent_id=excluded.assigned_agent_id,
                     dependencies_json=excluded.dependencies_json,
                     created_at=excluded.created_at""",
                (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                 str(item.assigned_agent_id) if item.assigned_agent_id else None,
                 _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
            )

    def save_work_item_with_audit(self, item: WorkItem, record: AuditRecord) -> str:
        """Persist a work item change and its audit evidence in one transaction."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT business_id FROM work_items WHERE id=?", (str(item.id),)
                ).fetchone()
                if existing is not None and existing["business_id"] != item.business_id:
                    raise ValueError("a work item's business unit is immutable")
                self._connection.execute(
                    """INSERT INTO work_items
                       (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         title=excluded.title, objective=excluded.objective,
                         department=excluded.department, state=excluded.state,
                         assigned_agent_id=excluded.assigned_agent_id,
                         dependencies_json=excluded.dependencies_json,
                         created_at=excluded.created_at""",
                    (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                     str(item.assigned_agent_id) if item.assigned_agent_id else None,
                     _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                )
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def save_work_items_with_audit(
        self, items: tuple[WorkItem, ...], records: tuple[AuditRecord, ...]
    ) -> None:
        """Persist a complete draft plan and all audit events atomically."""
        if not items or len(items) != len(records):
            raise ValueError("each planned work item requires one audit record")
        if len({item.id for item in items}) != len(items):
            raise ValueError("planned work item identifiers must be unique")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    self._connection.execute(
                        """INSERT INTO work_items
                           (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (str(item.id), item.title, item.objective, item.department, item.business_id,
                         item.state.value, str(item.assigned_agent_id) if item.assigned_agent_id else None,
                         _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                    )
                for record in records:
                    row = self._connection.execute(
                        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    previous_hash = row["event_hash"] if row else _ZERO_HASH
                    payload = _audit_payload(record, previous_hash)
                    self._connection.execute(
                        """INSERT INTO audit_events
                           (event_id,occurred_at,payload_json,previous_hash,event_hash)
                           VALUES(?,?,?,?,?)""",
                        (str(record.id), record.occurred_at.isoformat(), _json(payload),
                         previous_hash, _digest(payload)),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def approve_delegation_proposal(
        self, proposal_id: UUID, items: tuple[WorkItem, ...],
        records: tuple[AuditRecord, ...], *, parent_update: WorkItem | None = None,
    ) -> bool:
        """Atomically approve a draft proposal, materialize child tasks, and audit."""
        if not items or not records:
            raise ValueError("approved delegation requires child tasks and audit records")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                proposal = self._connection.execute(
                    "SELECT status FROM delegation_proposals WHERE id=?",
                    (str(proposal_id),),
                ).fetchone()
                if proposal is None or proposal["status"] != "draft":
                    self._connection.execute("ROLLBACK")
                    return False
                expected_ids = {
                    row["id"] for row in self._connection.execute(
                        "SELECT id FROM delegation_child_tasks WHERE proposal_id=? AND state='draft'",
                        (str(proposal_id),),
                    ).fetchall()
                }
                if expected_ids != {str(item.id) for item in items}:
                    self._connection.execute("ROLLBACK")
                    raise ValueError("materialized tasks do not match the proposal's draft children")
                if parent_update is not None:
                    parent_row = self._connection.execute(
                        "SELECT state,assigned_agent_id,department,business_id FROM work_items WHERE id=?",
                        (str(parent_update.id),),
                    ).fetchone()
                    if (
                        parent_row is None
                        or parent_row["state"] != TaskState.DRAFT.value
                        or parent_row["assigned_agent_id"] is not None
                        or parent_row["department"] != parent_update.department
                        or parent_row["business_id"] != parent_update.business_id
                        or any(item.business_id != parent_update.business_id for item in items)
                        or parent_update.state != TaskState.READY
                        or parent_update.assigned_agent_id is None
                        or set(parent_update.depends_on) != {item.id for item in items}
                    ):
                        self._connection.execute("ROLLBACK")
                        raise ValueError("manager synthesis parent must be an unassigned DRAFT task depending on every approved child")
                    changed = self._connection.execute(
                        """UPDATE work_items SET state=?,assigned_agent_id=?,dependencies_json=?
                           WHERE id=? AND state=? AND assigned_agent_id IS NULL""",
                        (parent_update.state.value, str(parent_update.assigned_agent_id),
                         _json([str(value) for value in parent_update.depends_on]),
                         str(parent_update.id), TaskState.DRAFT.value),
                    )
                    if changed.rowcount != 1:
                        self._connection.execute("ROLLBACK")
                        return False
                for item in items:
                    self._connection.execute(
                        """INSERT INTO work_items
                           (id,title,objective,department,business_id,state,assigned_agent_id,dependencies_json,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (str(item.id), item.title, item.objective, item.department, item.business_id, item.state.value,
                         str(item.assigned_agent_id) if item.assigned_agent_id else None,
                         _json([str(value) for value in item.depends_on]), item.created_at.isoformat()),
                    )
                for record in records:
                    row = self._connection.execute(
                        "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                    previous_hash = row["event_hash"] if row else _ZERO_HASH
                    payload = _audit_payload(record, previous_hash)
                    event_hash = _digest(payload)
                    self._connection.execute(
                        """INSERT INTO audit_events
                           (event_id,occurred_at,payload_json,previous_hash,event_hash)
                           VALUES(?,?,?,?,?)""",
                        (str(record.id), record.occurred_at.isoformat(), _json(payload),
                         previous_hash, event_hash),
                    )
                self._connection.execute(
                    "UPDATE delegation_child_tasks SET state='approved' WHERE proposal_id=? AND state='draft'",
                    (str(proposal_id),),
                )
                self._connection.execute(
                    "UPDATE delegation_proposals SET status='approved' WHERE id=? AND status='draft'",
                    (str(proposal_id),),
                )
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def save(self, deliverable: Any) -> None:
        """Idempotently stage a review-required artifact before its atomic audit transition."""
        if not deliverable.review_required:
            raise ValueError("worker deliverables must require review")
        values = (
            str(deliverable.work_item_id), deliverable.role_key, deliverable.content,
            deliverable.provider, deliverable.model, float(deliverable.cost_usd),
            deliverable.created_at.isoformat(), 1,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute(
                    "SELECT state FROM work_items WHERE id=?", (str(deliverable.work_item_id),)
                ).fetchone()
                if item is None or item["state"] != TaskState.IN_PROGRESS.value:
                    raise ValueError("artifact can only be staged for an in-progress work item")
                existing = self._connection.execute(
                    "SELECT * FROM deliverables WHERE id=?", (str(deliverable.id),)
                ).fetchone()
                if existing is not None:
                    old = (
                        existing["work_item_id"], existing["role_key"], existing["content"],
                        existing["provider"], existing["model"], float(existing["cost_usd"]),
                        existing["created_at"], int(existing["review_required"]),
                    )
                    if old != values:
                        raise ValueError("deliverable ID already exists with different content")
                else:
                    self._connection.execute(
                        "INSERT INTO deliverables (id,work_item_id,role_key,content,provider,model,cost_usd,created_at,review_required) VALUES(?,?,?,?,?,?,?,?,?)",
                        (str(deliverable.id), *values),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def save_deliverable_with_audit(self, deliverable: Any, record: AuditRecord) -> bool:
        """Persist a draft, move its task to review, and audit atomically."""
        if not deliverable.review_required:
            raise ValueError("worker deliverables must require review")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute("SELECT state FROM work_items WHERE id=?", (str(deliverable.work_item_id),)).fetchone()
                if item is None or item["state"] != TaskState.IN_PROGRESS.value:
                    self._connection.execute("ROLLBACK")
                    return False
                values = (str(deliverable.work_item_id), deliverable.role_key, deliverable.content, deliverable.provider, deliverable.model, float(deliverable.cost_usd), deliverable.created_at.isoformat(), 1)
                existing = self._connection.execute("SELECT * FROM deliverables WHERE id=?", (str(deliverable.id),)).fetchone()
                if existing is not None:
                    old = (existing["work_item_id"], existing["role_key"], existing["content"], existing["provider"], existing["model"], float(existing["cost_usd"]), existing["created_at"], int(existing["review_required"]))
                    if old != values:
                        raise ValueError("deliverable ID already exists with different content")
                else:
                    self._connection.execute("INSERT INTO deliverables (id,work_item_id,role_key,content,provider,model,cost_usd,created_at,review_required) VALUES(?,?,?,?,?,?,?,?,?)", (str(deliverable.id), *values))
                self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (TaskState.REVIEW.value, str(deliverable.work_item_id), TaskState.IN_PROGRESS.value))
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def review_work_item_with_audit(self, work_item_id: UUID, *, approved: bool, rationale: str, record: AuditRecord) -> TaskState | None:
        """Record an owner review decision and transition REVIEW atomically."""
        if not isinstance(approved, bool) or not rationale.strip() or len(rationale) > 2000:
            raise ValueError("review decision and a 1-2000 character rationale are required")
        target = TaskState.COMPLETED if approved else TaskState.READY
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                item = self._connection.execute("SELECT state FROM work_items WHERE id=?", (str(work_item_id),)).fetchone()
                if item is None or item["state"] != TaskState.REVIEW.value:
                    self._connection.execute("ROLLBACK")
                    return None
                count = self._connection.execute("SELECT COUNT(*) AS n FROM deliverables WHERE work_item_id=? AND review_required=1", (str(work_item_id),)).fetchone()["n"]
                if int(count) < 1:
                    self._connection.execute("ROLLBACK")
                    raise ValueError("work item has no review-required deliverable")
                self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (target.value, str(work_item_id), TaskState.REVIEW.value))
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return target
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
    def fail_work_item_with_audit(self, work_item_id: UUID, record: AuditRecord) -> bool:
        """Move an in-progress task to failed only after its queue exhausts retries."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._connection.execute("UPDATE work_items SET state=? WHERE id=? AND state=?", (TaskState.FAILED.value, str(work_item_id), TaskState.IN_PROGRESS.value))
                if cursor.rowcount != 1:
                    self._connection.execute("ROLLBACK")
                    return False
                row = self._connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute("INSERT INTO audit_events (event_id,occurred_at,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?)", (str(record.id), record.occurred_at.isoformat(), _json(payload), previous_hash, event_hash))
                self._connection.execute("COMMIT")
                return True
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def backup_to(self, destination: str | Path) -> Path:
        """Create and integrity-check a consistent SQLite snapshot at destination.

        The backup API includes committed WAL content and does not copy a live
        database file byte-for-byte. The caller is responsible for protecting
        and retaining the resulting file as sensitive company data.
        """
        destination_path = Path(destination).expanduser().resolve()
        if self.database != ":memory:":
            source_path = Path(self.database).expanduser().resolve()
            if destination_path == source_path:
                raise ValueError("backup destination must differ from the live database")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(destination_path), timeout=10)
            try:
                self._connection.backup(target, pages=256, sleep=0.05)
                integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError("SQLite backup failed its integrity check")
            except Exception:
                target.close()
                destination_path.unlink(missing_ok=True)
                raise
            else:
                target.close()
        return destination_path

    def list_deliverables(self, work_item_id: UUID) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM deliverables WHERE work_item_id=? ORDER BY created_at,id", (str(work_item_id),)).fetchall()
        return tuple({"id": row["id"], "work_item_id": row["work_item_id"], "role_key": row["role_key"], "content": row["content"], "provider": row["provider"], "model": row["model"], "cost_usd": float(row["cost_usd"]), "created_at": row["created_at"], "review_required": bool(row["review_required"])} for row in rows)

    def get_work_item(self, item_id: UUID) -> WorkItem | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM work_items WHERE id=?", (str(item_id),)
            ).fetchone()
        if row is None:
            return None
        return WorkItem(
            id=UUID(row["id"]), title=row["title"], objective=row["objective"],
            department=row["department"], state=TaskState(row["state"]),
            assigned_agent_id=UUID(row["assigned_agent_id"]) if row["assigned_agent_id"] else None,
            depends_on=tuple(UUID(value) for value in json.loads(row["dependencies_json"])),
            created_at=datetime.fromisoformat(row["created_at"]),
            business_id=row["business_id"] if "business_id" in row.keys() else "core",
        )

    def list_work_items(
        self, *, state: TaskState | None = None, business_id: str | None = None,
        limit: int = 100,
    ) -> tuple[WorkItem, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        clauses, values = [], []
        if state is not None:
            clauses.append("state=?")
            values.append(state.value)
        if business_id is not None:
            from .domain import BUSINESS_UNIT_IDS
            if business_id not in BUSINESS_UNIT_IDS:
                raise ValueError(f"unknown business unit: {business_id}")
            clauses.append("business_id=?")
            values.append(business_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(limit)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT id FROM work_items{where} ORDER BY created_at,id LIMIT ?",
                tuple(values),
            ).fetchall()
        return tuple(self.get_work_item(UUID(row["id"])) for row in rows)

    def append_audit_record(self, record: AuditRecord) -> str:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else _ZERO_HASH
                payload = _audit_payload(record, previous_hash)
                event_hash = _digest(payload)
                self._connection.execute(
                    """INSERT INTO audit_events
                       (event_id,occurred_at,payload_json,previous_hash,event_hash)
                       VALUES(?,?,?,?,?)""",
                    (str(record.id), record.occurred_at.isoformat(), _json(payload),
                     previous_hash, event_hash),
                )
                self._connection.execute("COMMIT")
                return event_hash
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def verify_audit_chain(self) -> bool:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json,previous_hash,event_hash FROM audit_events ORDER BY sequence"
            ).fetchall()
        expected_previous = _ZERO_HASH
        for row in rows:
            payload = json.loads(row["payload_json"])
            if row["previous_hash"] != expected_previous:
                return False
            if payload.get("previous_hash") != expected_previous:
                return False
            if _digest(payload) != row["event_hash"]:
                return False
            expected_previous = row["event_hash"]
        return True

    def audit_event_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()
        return int(row["n"])
