"""Versioned, owner-controlled specialist instruction addenda.

The pinned upstream profile remains immutable. Approved addenda are layered beneath
OS governance, versioned in SQLite, and activated only through an owner-authenticated
API after a passing static screen. History rows are immutable; rollback moves a head.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect
from ai_os.registry import get_agent, load_agent_profile


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _profile_hash(agent_id: str) -> str:
    agent = get_agent(agent_id)
    if agent is None:
        raise LookupError("Agent not found")
    profile = load_agent_profile(agent_id) or agent.description
    return hashlib.sha256(profile.encode("utf-8")).hexdigest()


def _ensure_head(db, agent_id: str, profile_hash: str) -> dict:
    head = db.execute(
        """SELECT h.agent_id,h.active_version_id,v.version_number,v.content,
                  v.content_sha256,v.base_profile_sha256,v.created_at,v.source_proposal_id
           FROM agent_instruction_heads h
           JOIN agent_instruction_versions v ON v.id=h.active_version_id
           WHERE h.agent_id=?""",
        (agent_id,),
    ).fetchone()
    if head is not None:
        result = dict(head)
        result["profile_compatible"] = result["base_profile_sha256"] == profile_hash
        return result

    version_id = str(uuid4())
    db.execute(
        """INSERT INTO agent_instruction_versions
           (id,agent_id,version_number,content,content_sha256,base_profile_sha256,
            parent_version_id,source_proposal_id,created_at,created_by)
           VALUES (?,?,1,'',?,?,NULL,NULL,?,'system:baseline')""",
        (version_id, agent_id, hashlib.sha256(b"").hexdigest(), profile_hash, _now()),
    )
    db.execute(
        "INSERT INTO agent_instruction_heads (agent_id,active_version_id,updated_at) VALUES (?,?,?)",
        (agent_id, version_id, _now()),
    )
    return {
        "agent_id": agent_id, "active_version_id": version_id, "version_number": 1,
        "content": "", "content_sha256": hashlib.sha256(b"").hexdigest(),
        "base_profile_sha256": profile_hash, "created_at": _now(),
        "source_proposal_id": None, "profile_compatible": True,
    }


def get_active_instruction(agent_id: str) -> dict:
    """Return the active addendum, failing closed if its upstream profile drifted."""
    profile_hash = _profile_hash(agent_id)
    with connect() as db:
        head = _ensure_head(db, agent_id, profile_hash)
    if not head["profile_compatible"]:
        return {**head, "content": "", "notice": "Upstream profile changed; active addendum withheld pending owner review."}
    return {**head, "notice": "Versioned owner-approved addendum; OS governance always takes precedence."}


def get_instruction_history(agent_id: str, *, limit: int = 30) -> list[dict]:
    _profile_hash(agent_id)
    bounded = max(1, min(int(limit), 100))
    with connect() as db:
        rows = db.execute(
            """SELECT v.*,CASE WHEN h.active_version_id=v.id THEN 1 ELSE 0 END AS active
               FROM agent_instruction_versions v
               LEFT JOIN agent_instruction_heads h ON h.agent_id=v.agent_id
               WHERE v.agent_id=? ORDER BY v.version_number DESC LIMIT ?""",
            (agent_id, bounded),
        ).fetchall()
    return [{**dict(row), "active": bool(row["active"])} for row in rows]


def activate_tested_proposal(proposal_id: str, *, actor: str) -> dict | None:
    """Activate a proposal only after owner-authenticated call and a matching passing test."""
    with connect() as db:
        proposal = db.execute(
            "SELECT * FROM improvement_proposals WHERE id=?", (proposal_id,)
        ).fetchone()
        if proposal is None:
            return None
        if proposal["status"] != "approved_for_testing":
            raise ValueError("Proposal must be owner-approved for testing before activation.")
        already_activated = db.execute(
            "SELECT id FROM agent_instruction_versions WHERE source_proposal_id=? LIMIT 1",
            (proposal_id,),
        ).fetchone()
        if already_activated:
            raise ValueError("This proposal has already created an instruction version; draft a new proposal for another change.")
        content = proposal["proposed_change"]
        if not isinstance(content, str) or not content.strip() or len(content) > 4000:
            raise ValueError("Instruction addendum is empty or exceeds the 4000-character limit.")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        test = db.execute(
            """SELECT * FROM improvement_test_runs WHERE proposal_id=?
               ORDER BY created_at DESC,id DESC LIMIT 1""",
            (proposal_id,),
        ).fetchone()
        if test is None or not test["passed"] or test["candidate_sha256"] != digest:
            raise ValueError("The latest static test must pass for the exact current proposal text.")
        profile_hash = _profile_hash(proposal["agent_id"])
        head = _ensure_head(db, proposal["agent_id"], profile_hash)
        if not head["profile_compatible"]:
            raise ValueError("Upstream specialist profile changed; review the baseline before activation.")
        next_number = db.execute(
            "SELECT COALESCE(MAX(version_number),0)+1 FROM agent_instruction_versions WHERE agent_id=?",
            (proposal["agent_id"],),
        ).fetchone()[0]
        version_id = str(uuid4())
        created_at = _now()
        db.execute(
            """INSERT INTO agent_instruction_versions
               (id,agent_id,version_number,content,content_sha256,base_profile_sha256,
                parent_version_id,source_proposal_id,created_at,created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (version_id, proposal["agent_id"], next_number, content, digest,
             profile_hash, head["active_version_id"], proposal_id, created_at, actor),
        )
        db.execute(
            """UPDATE agent_instruction_heads SET active_version_id=?,updated_at=?
               WHERE agent_id=?""",
            (version_id, created_at, proposal["agent_id"]),
        )
    return {
        "id": version_id, "agent_id": proposal["agent_id"],
        "version_number": next_number, "content": content,
        "content_sha256": digest, "base_profile_sha256": profile_hash,
        "parent_version_id": head["active_version_id"],
        "source_proposal_id": proposal_id, "created_at": created_at,
        "created_by": actor, "active": True,
    }


def rollback_instruction(agent_id: str, *, actor: str) -> dict | None:
    """Move the active pointer to the immutable parent version; never delete history."""
    profile_hash = _profile_hash(agent_id)
    with connect() as db:
        head = _ensure_head(db, agent_id, profile_hash)
        if not head["profile_compatible"]:
            raise ValueError("Upstream specialist profile changed; rollback requires baseline review.")
        active = db.execute(
            "SELECT parent_version_id FROM agent_instruction_versions WHERE id=? AND agent_id=?",
            (head["active_version_id"], agent_id),
        ).fetchone()
        if active is None or not active["parent_version_id"]:
            raise ValueError("No earlier instruction version is available to restore.")
        target_id = active["parent_version_id"]
        target = db.execute(
            "SELECT * FROM agent_instruction_versions WHERE id=? AND agent_id=?",
            (target_id, agent_id),
        ).fetchone()
        if target is None:
            raise ValueError("Previous instruction version is missing.")
        db.execute(
            "UPDATE agent_instruction_heads SET active_version_id=?,updated_at=? WHERE agent_id=?",
            (target_id, _now(), agent_id),
        )
    return {
        "id": target["id"], "agent_id": agent_id,
        "version_number": target["version_number"], "content": target["content"],
        "content_sha256": target["content_sha256"],
        "base_profile_sha256": target["base_profile_sha256"],
        "parent_version_id": target["parent_version_id"],
        "source_proposal_id": target["source_proposal_id"],
        "created_at": target["created_at"], "created_by": target["created_by"],
        "active": True, "rolled_back_by": actor,
    }


def list_instruction_heads(limit: int = 300) -> list[dict]:
    """List only agents with a materialized instruction baseline/head."""
    bounded = max(1, min(int(limit), 500))
    with connect() as db:
        rows = db.execute(
            """SELECT h.agent_id,h.active_version_id,v.version_number,v.content_sha256,
                      v.base_profile_sha256,v.source_proposal_id,h.updated_at
               FROM agent_instruction_heads h
               JOIN agent_instruction_versions v ON v.id=h.active_version_id
               ORDER BY h.agent_id LIMIT ?""",
            (bounded,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["profile_compatible"] = item["base_profile_sha256"] == _profile_hash(item["agent_id"])
        except LookupError:
            item["profile_compatible"] = False
        result.append(item)
    return result
