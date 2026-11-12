"""Agent-profile persistence operations for the OpenCompany SQLite store."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .domain import AgentProfile, AgentState, AuditRecord
from .persistence_utils import _ZERO_HASH, _audit_payload, _digest, _json


class AgentPersistenceMixin:
    """Repository methods for agent profiles, revisions and audited activation."""

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

