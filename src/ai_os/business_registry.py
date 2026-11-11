"""Owner-controlled registry for expandable OpenCompany business units."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from uuid import uuid4
from ai_os.db import connect

BUILTIN_BUSINESSES = {
    "core": {"name": "AIOS Core", "business_type": "internal", "description": "Internal company operations; not a customer business unit."},
    "physical-agency": {"name": "Physical Products Agency", "business_type": "physical-agency", "description": "Third-party physical-product supplier and manufacturer agency."},
    "physical-brand": {"name": "Own Physical Products Brand", "business_type": "physical-brand", "description": "Owner's separate physical-products brand."},
    "digital-products": {"name": "Digital Products", "business_type": "digital-products", "description": "Downloadable digital products and licensing."},
}
BUSINESS_IDS = set(BUILTIN_BUSINESSES)
_SLUG = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")

def refresh_business_ids() -> set[str]:
    with connect() as db:
        rows = db.execute("SELECT id FROM business_units WHERE status='active'").fetchall()
    BUSINESS_IDS.clear()
    BUSINESS_IDS.update(BUILTIN_BUSINESSES)
    BUSINESS_IDS.update(row["id"] for row in rows)
    return BUSINESS_IDS

def list_businesses(include_archived: bool = False) -> list[dict]:
    result = []
    for business_id, item in BUILTIN_BUSINESSES.items():
        result.append({"id": business_id, **item, "status": "active", "built_in": True})
    query = "SELECT id,name,business_type,description,status,created_at FROM business_units"
    if not include_archived:
        query += " WHERE status='active'"
    query += " ORDER BY created_at,id"
    with connect() as db:
        rows = db.execute(query).fetchall()
    result.extend([{**dict(row), "built_in": False} for row in rows])
    return result

def get_business(business_id: str) -> dict | None:
    if business_id in BUILTIN_BUSINESSES:
        return {"id": business_id, **BUILTIN_BUSINESSES[business_id], "status": "active", "built_in": True}
    with connect() as db:
        row = db.execute(
            "SELECT id,name,business_type,description,status,created_at FROM business_units WHERE id=?",
            (business_id,),
        ).fetchone()
    return {**dict(row), "built_in": False} if row else None


def create_business(name: str, business_type: str, description: str = "") -> dict:
    clean_name = " ".join((name or "").split())[:120]
    clean_type = (business_type or "general").strip().lower()
    clean_description = (description or "").strip()[:3000]
    if len(clean_name) < 2:
        raise ValueError("Business name must contain at least two characters.")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}[a-z0-9]", clean_type):
        raise ValueError("Business type must be a short lowercase slug.")
    base = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-")[:48].strip("-")
    if not base or not base[0].isalpha():
        base = "venture-" + base
    business_id = base
    with connect() as db:
        existing = {row["id"] for row in db.execute("SELECT id FROM business_units").fetchall()}
        existing.update(BUILTIN_BUSINESSES)
        suffix = 2
        while business_id in existing:
            business_id = f"{base[:54]}-{suffix}"
            suffix += 1
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO business_units(id,name,business_type,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (business_id, clean_name, clean_type, clean_description, "active", now, now),
        )
    BUSINESS_IDS.add(business_id)
    return {"id": business_id, "name": clean_name, "business_type": clean_type,
            "description": clean_description, "status": "active", "built_in": False}

def require_business(business_id: str, allow_core: bool = True) -> str:
    scope = (business_id or "").strip()
    if scope not in BUSINESS_IDS:
        refresh_business_ids()
    if scope not in BUSINESS_IDS or (not allow_core and scope == "core"):
        raise ValueError("Unknown or inactive business unit.")
    return scope
