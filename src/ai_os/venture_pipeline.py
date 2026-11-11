"""Company-wide venture opportunity pipeline.

This portfolio-level pipeline is intentionally separate from individual business-unit
records. Research and recommendations do not authorize spending or external launch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect

STATUSES = {
    "idea", "research_queued", "assessed", "shortlisted",
    "launch_approved", "launched", "rejected", "paused",
}
DIMENSIONS = ("demand", "competition", "economics", "distribution", "execution", "risk")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(row) -> dict:
    item = dict(row)
    for field in ("assessment_json", "evidence_json"):
        raw = item.pop(field, "{}" if field == "assessment_json" else "[]")
        item[field.removesuffix("_json")] = json.loads(raw or ("{}" if field == "assessment_json" else "[]"))
    return item


def score_assessment(assessment: dict) -> dict:
    """Calculate a provisional score only from explicitly supplied 0-5 ratings."""
    ratings = assessment.get("ratings") if isinstance(assessment, dict) else None
    if not isinstance(ratings, dict):
        return {"score": None, "coverage": 0, "dimensions": list(DIMENSIONS), "label": "not_scored"}
    valid = {key: ratings.get(key) for key in DIMENSIONS
             if isinstance(ratings.get(key), (int, float)) and 0 <= ratings[key] <= 5}
    coverage = len(valid)
    if coverage != len(DIMENSIONS):
        return {"score": None, "coverage": coverage, "dimensions": list(DIMENSIONS), "label": "incomplete_assessment"}
    sources = assessment.get("source_urls") or []
    verified_urls = [url for url in sources if isinstance(url, str) and url.startswith("https://")]
    score = round(sum(float(valid[key]) for key in DIMENSIONS) / len(DIMENSIONS) * 20, 1)
    return {
        "score": score,
        "coverage": coverage,
        "dimensions": list(DIMENSIONS),
        "source_count": len(set(verified_urls)),
        "label": "provisional_research_score",
        "warning": "Ratings are analyst assessments, not independently verified facts. Review every source and assumption.",
    }


def create_opportunity(payload: dict) -> dict:
    title = " ".join(str(payload.get("title") or "").split())[:160]
    thesis = str(payload.get("thesis") or "").strip()[:6000]
    if len(title) < 3 or len(thesis) < 20:
        raise ValueError("Provide an opportunity title and a thesis of at least 20 characters.")
    item = {
        "id": str(uuid4()), "title": title, "thesis": thesis,
        "customer_segment": str(payload.get("customer_segment") or "").strip()[:500],
        "problem": str(payload.get("problem") or "").strip()[:1000],
        "revenue_model": str(payload.get("revenue_model") or "unknown").strip()[:100],
        "market_scope": str(payload.get("market_scope") or "global").strip()[:120],
        "status": "idea", "assessment_json": "{}", "evidence_json": "[]",
        "research_task_id": None, "business_id": None,
        "created_at": _now(), "updated_at": _now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO venture_opportunities
            (id,title,thesis,customer_segment,problem,revenue_model,market_scope,status,
             assessment_json,evidence_json,research_task_id,business_id,created_at,updated_at)
            VALUES (:id,:title,:thesis,:customer_segment,:problem,:revenue_model,:market_scope,:status,
             :assessment_json,:evidence_json,:research_task_id,:business_id,:created_at,:updated_at)""",
            item,
        )
    return _decode(item)


def list_opportunities(status: str | None = None) -> list[dict]:
    with connect() as db:
        if status:
            rows = db.execute(
                "SELECT * FROM venture_opportunities WHERE status=? ORDER BY updated_at DESC LIMIT 200",
                (status,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM venture_opportunities ORDER BY updated_at DESC LIMIT 200"
            ).fetchall()
    return [_decode(row) for row in rows]


def get_opportunity(opportunity_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM venture_opportunities WHERE id=?", (opportunity_id,)).fetchone()
    return _decode(row) if row else None


def queue_research(opportunity_id: str, task_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM venture_opportunities WHERE id=?", (opportunity_id,)).fetchone()
        if row is None:
            raise LookupError("Venture opportunity not found.")
        if row["status"] not in {"idea", "shortlisted", "assessed", "paused"}:
            raise ValueError("This opportunity is not eligible for a new research run.")
        updated = _now()
        db.execute(
            "UPDATE venture_opportunities SET status='research_queued',research_task_id=?,updated_at=? WHERE id=?",
            (task_id, updated, opportunity_id),
        )
    return get_opportunity(opportunity_id)


def save_assessment(opportunity_id: str, assessment: dict, evidence: list) -> dict:
    if not isinstance(assessment, dict):
        raise ValueError("Assessment must be a structured object.")
    for key in DIMENSIONS:
        rating = (assessment.get("ratings") or {}).get(key)
        if rating is not None and (not isinstance(rating, (int, float)) or not 0 <= rating <= 5):
            raise ValueError(f"Assessment rating '{key}' must be between 0 and 5.")
    clean_evidence = []
    for item in evidence[:100]:
        if isinstance(item, dict) and str(item.get("url") or "").startswith("https://"):
            clean_evidence.append({
                "url": str(item["url"])[:1000],
                "claim": str(item.get("claim") or "")[:1000],
                "source_date": str(item.get("source_date") or "")[:80],
            })
    enriched = dict(assessment)
    enriched["scorecard"] = score_assessment(enriched)
    with connect() as db:
        row = db.execute("SELECT id FROM venture_opportunities WHERE id=?", (opportunity_id,)).fetchone()
        if row is None:
            raise LookupError("Venture opportunity not found.")
        db.execute(
            """UPDATE venture_opportunities SET assessment_json=?,evidence_json=?,
            status='assessed',updated_at=? WHERE id=?""",
            (json.dumps(enriched, ensure_ascii=False), json.dumps(clean_evidence, ensure_ascii=False),
             _now(), opportunity_id),
        )
    return get_opportunity(opportunity_id)


def decide_opportunity(opportunity_id: str, decision: str, notes: str = "") -> dict:
    allowed = {"shortlisted", "launch_approved", "rejected", "paused"}
    if decision not in allowed:
        raise ValueError("Unsupported venture decision.")
    item = get_opportunity(opportunity_id)
    if not item:
        raise LookupError("Venture opportunity not found.")
    if decision == "launch_approved":
        scorecard = (item.get("assessment") or {}).get("scorecard") or {}
        if scorecard.get("coverage") != len(DIMENSIONS) or scorecard.get("source_count", 0) < 3:
            raise ValueError("Launch approval requires all six assessment dimensions and at least three HTTPS sources.")
    with connect() as db:
        db.execute(
            "UPDATE venture_opportunities SET status=?,updated_at=? WHERE id=?",
            (decision, _now(), opportunity_id),
        )
        if notes.strip():
            db.execute(
                "UPDATE venture_opportunities SET assessment_json=? WHERE id=?",
                (json.dumps({**item.get("assessment", {}), "owner_decision_notes": notes.strip()[:3000]}), opportunity_id),
            )
    return get_opportunity(opportunity_id)


def mark_launched(opportunity_id: str, business_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT status FROM venture_opportunities WHERE id=?", (opportunity_id,)).fetchone()
        if row is None:
            raise LookupError("Venture opportunity not found.")
        if row["status"] != "launch_approved":
            raise ValueError("Only an owner-approved opportunity can become a registered business unit.")
        db.execute(
            "UPDATE venture_opportunities SET status='launched',business_id=?,updated_at=? WHERE id=?",
            (business_id, _now(), opportunity_id),
        )
    return get_opportunity(opportunity_id)
