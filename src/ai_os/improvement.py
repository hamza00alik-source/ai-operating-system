"""Evidence-linked, proposal-only continuous improvement workflow."""
import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect


_CHECK_GUIDANCE = {
    "summary": ("Require concise, non-empty task summaries and a completion rationale.",
                "Reduce incomplete or ambiguous specialist reports."),
    "completed_has_evidence": ("Require task-relevant evidence before marking a step completed.",
                               "Improve evidence completeness; factual accuracy still needs source review."),
    "blocked_has_reason": ("Require a concrete blocker and the missing prerequisite in blocked reports.",
                           "Make blocked work easier for the CEO to diagnose."),
    "evidence_shape": ("Require evidence entries to be specific, non-empty strings with source context.",
                       "Improve consistency of evidence records."),
    "blockers_shape": ("Require blockers to be actionable, non-empty explanations.",
                       "Improve blocker clarity."),
    "no_external_action_claim": ("Reinforce the no-external-actions boundary and require agents to label recommendations as unexecuted.",
                                 "Reduce unsupported claims that external actions occurred."),
    "status": ("Require only the supported completed or blocked statuses, with explicit criteria.",
               "Reduce invalid workflow status reports."),
    "object": ("Require a valid structured JSON object matching the specialist report contract.",
               "Reduce malformed report output."),
}


def draft_improvement_proposals(*, limit: int = 100) -> list[dict]:
    """Draft one proposal per repeated failed rubric check; never change live prompts."""
    bounded = max(1, min(int(limit), 500))
    with connect() as db:
        rows = db.execute(
            "SELECT id,agent_id,score,critical_failures_json,checks_json,created_at "
            "FROM agent_evaluations ORDER BY created_at DESC,id DESC LIMIT ?",
            (bounded,),
        ).fetchall()
        grouped: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            for check in json.loads(row["checks_json"]):
                key = check.get("key")
                if not check.get("passed") and key in _CHECK_GUIDANCE:
                    grouped.setdefault((row["agent_id"], key), []).append({
                        "evaluation_id": row["id"], "score": row["score"],
                        "created_at": row["created_at"],
                    })
        created = []
        for (agent_id, check_key), evidence in grouped.items():
            if len(evidence) < 2:
                continue
            existing = db.execute(
                """SELECT id FROM improvement_proposals
                WHERE agent_id=? AND title=? AND status IN ('candidate','approved_for_testing')
                LIMIT 1""",
                (agent_id, f"Improve {check_key.replace('_', ' ')}"),
            ).fetchone()
            if existing:
                continue
            change, impact = _CHECK_GUIDANCE[check_key]
            item = {
                "id": str(uuid4()), "agent_id": agent_id,
                "title": f"Improve {check_key.replace('_', ' ')}",
                "problem": f"The deterministic report rubric recorded {len(evidence)} failures for check '{check_key}' in the recent evaluation sample.",
                "evidence_json": json.dumps(evidence, separators=(",", ":")),
                "proposed_change": change, "expected_impact": impact,
                "status": "candidate",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            db.execute(
                """INSERT INTO improvement_proposals
                (id,agent_id,title,problem,evidence_json,proposed_change,expected_impact,status,created_at)
                VALUES (:id,:agent_id,:title,:problem,:evidence_json,:proposed_change,:expected_impact,:status,:created_at)""",
                item,
            )
            created.append(_decode(item))
    return created


def _decode(row) -> dict:
    item = dict(row)
    item["evidence"] = json.loads(item.pop("evidence_json"))
    return item


def list_improvement_proposals(*, status: str | None = None, limit: int = 100) -> list[dict]:
    bounded = max(1, min(int(limit), 500))
    with connect() as db:
        if status:
            rows = db.execute(
                "SELECT * FROM improvement_proposals WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, bounded),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM improvement_proposals ORDER BY created_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
    return [_decode(row) for row in rows]


def review_improvement_proposal(proposal_id: str, *, decision: str, actor: str, note: str = "") -> dict | None:
    if decision not in {"approved_for_testing", "rejected"}:
        raise ValueError("Decision must be approved_for_testing or rejected.")
    with connect() as db:
        row = db.execute("SELECT * FROM improvement_proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None:
            return None
        if row["status"] != "candidate":
            raise ValueError("Only candidate proposals can be reviewed once.")
        db.execute(
            """UPDATE improvement_proposals SET status=?,reviewed_at=?,reviewed_by=?,review_note=?
            WHERE id=? AND status='candidate'""",
            (decision, datetime.now(timezone.utc).isoformat(), actor, note[:2000], proposal_id),
        )
        updated = db.execute("SELECT * FROM improvement_proposals WHERE id=?", (proposal_id,)).fetchone()
    return _decode(updated)
