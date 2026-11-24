"""Owner-supervised business operations and code-asset inventory."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
import json
import re
from urllib.parse import urlparse

from ai_os.db import connect
from ai_os.brain import BUSINESS_IDS


def _scope(value: str = "core") -> str:
    scope = (value or "core").strip()
    if scope not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    return scope


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: str, limit: int = 500) -> str:
    value = " ".join(str(value or "").split()).strip()
    if len(value) > limit:
        raise ValueError(f"Field exceeds {limit} characters.")
    return value


def _url(value: str, allow_empty: bool = True) -> str:
    value = _clean(value, 2048)
    if not value and allow_empty:
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("URLs must use HTTPS.")
    return value


def list_records(kind: str, limit: int = 200, business_id: str = "core") -> list[dict]:
    if kind not in {"customer", "expense", "revenue"}:
        raise ValueError("Unsupported record type.")
    scope = _scope(business_id)
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM business_records WHERE record_type=? AND business_id=? ORDER BY created_at DESC LIMIT ?",
            (kind, scope, max(1, min(limit, 500))),
        ).fetchall()
    return [dict(row) for row in rows]


def create_record(kind: str, payload: dict) -> dict:
    if kind not in {"customer", "expense", "revenue"}:
        raise ValueError("Unsupported record type.")
    scope = _scope(payload.get("business_id", "core"))
    title = _clean(payload.get("title"), 160)
    if not title:
        raise ValueError("A title or customer name is required.")
    amount = payload.get("amount")
    if amount is not None:
        try:
            amount = round(float(amount), 2)
        except (TypeError, ValueError) as exc:
            raise ValueError("Amount must be a valid number.") from exc
        if amount < 0 or amount > 1_000_000_000:
            raise ValueError("Amount is outside the supported range.")
    currency = _clean(payload.get("currency", "USD"), 3).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Currency must be a three-letter ISO code.")
    status = "recorded"
    verified = 0
    if kind == "expense":
        status = "awaiting_owner_approval"
    elif kind == "revenue":
        # Never count unverified/expected revenue as earned.
        verified = 1 if payload.get("verified_payment") is True else 0
        status = "payment_verified" if verified else "unverified_not_counted"
    approval_id = str(uuid4()) if kind == "expense" else None
    record = {
        "id": str(uuid4()), "business_id": scope, "record_type": kind, "title": title,
        "amount": amount, "currency": currency,
        "status": status, "verified": verified, "approval_id": approval_id,
        "contact": _clean(payload.get("contact"), 200),
        "notes": _clean(payload.get("notes"), 2000),
        "created_at": now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO business_records
            (id,business_id,record_type,title,amount,currency,status,verified,approval_id,contact,notes,created_at)
            VALUES (:id,:business_id,:record_type,:title,:amount,:currency,:status,:verified,:approval_id,:contact,:notes,:created_at)""",
            record,
        )
        if approval_id:
            db.execute(
                """INSERT INTO approvals (id,task_id,business_id,action,details,status,created_at,decided_at)
                VALUES (?,NULL,?,?,?,?, ?,NULL)""",
                (approval_id, scope, "review_business_expense",
                 "Review expense " + record["id"] + ": " + title + " — " + str(amount) + " " + currency + ". No payment is initiated.",
                 "pending", record["created_at"]),
            )
    return record


def business_summary(business_id: str = "core") -> dict:
    scope = _scope(business_id)
    with connect() as db:
        expenses = db.execute(
            "SELECT currency, SUM(amount) total, COUNT(*) n FROM business_records WHERE business_id=? AND record_type='expense' GROUP BY currency", (scope,)
        ).fetchall()
        revenue = db.execute(
            """SELECT currency, SUM(amount) total, COUNT(*) n FROM business_records
            WHERE business_id=? AND record_type='revenue' AND verified=1 GROUP BY currency""", (scope,)
        ).fetchall()
        revenue_mtd = db.execute(
            """SELECT currency, SUM(amount) total, COUNT(*) n FROM business_records
            WHERE business_id=? AND record_type='revenue' AND verified=1 AND substr(created_at,1,7)=?
            GROUP BY currency""",
            (scope, now()[:7]),
        ).fetchall()
        customers = db.execute(
            "SELECT COUNT(*) n FROM business_records WHERE business_id=? AND record_type='customer'", (scope,)
        ).fetchone()["n"]
        pending_expenses = db.execute(
            "SELECT COUNT(*) n FROM business_records WHERE business_id=? AND record_type='expense' AND status='awaiting_owner_approval'", (scope,)
        ).fetchone()["n"]
    return {
        "business_id": scope,
        "customers": customers,
        "verified_revenue_by_currency": [dict(x) for x in revenue],
        "verified_revenue_mtd_by_currency": [dict(x) for x in revenue_mtd],
        "expenses_by_currency": [dict(x) for x in expenses],
        "expenses_awaiting_owner_approval": pending_expenses,
        "revenue_policy": "Only owner-marked verified payments are included. Expected or unverified revenue is excluded.",
        "expense_policy": "Expense entries are recorded as awaiting owner approval; this system does not initiate payments.",
    }


def list_assets(limit: int = 500) -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM code_assets ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 1000)),)).fetchall()
    return [dict(x) for x in rows]


def create_asset(payload: dict) -> dict:
    name = _clean(payload.get("name"), 180)
    if not name:
        raise ValueError("Asset name is required.")
    repo_url = _url(payload.get("repository_url", ""))
    asset_path = _clean(payload.get("path"), 500)
    token_estimate = payload.get("token_estimate")
    if token_estimate is not None:
        try:
            token_estimate = int(token_estimate)
        except (TypeError, ValueError) as exc:
            raise ValueError("Token estimate must be an integer.") from exc
        if token_estimate < 0:
            raise ValueError("Token estimate cannot be negative.")
    item = {
        "id": str(uuid4()), "name": name, "repository_url": repo_url,
        "path": asset_path, "asset_type": _clean(payload.get("asset_type", "source_code"), 50),
        "ownership_status": _clean(payload.get("ownership_status", "unverified"), 50),
        "license": _clean(payload.get("license", "unknown"), 100),
        "dependency_review": _clean(payload.get("dependency_review", "not_reviewed"), 50),
        "token_estimate": token_estimate,
        "token_method": _clean(payload.get("token_method", "not_measured"), 100),
        "git_history_tokens": None,
        "notes": _clean(payload.get("notes"), 2000),
        "created_at": now(), "updated_at": now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO code_assets
            (id,name,repository_url,path,asset_type,ownership_status,license,dependency_review,
             token_estimate,token_method,git_history_tokens,notes,created_at,updated_at)
            VALUES (:id,:name,:repository_url,:path,:asset_type,:ownership_status,:license,
             :dependency_review,:token_estimate,:token_method,:git_history_tokens,:notes,:created_at,:updated_at)""",
            item,
        )
    return item


def list_license_offers(limit: int = 200) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """SELECT o.*, a.name AS asset_name FROM license_offers o
            LEFT JOIN code_assets a ON a.id=o.asset_id ORDER BY o.created_at DESC LIMIT ?""",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [dict(x) for x in rows]


def create_license_offer(payload: dict) -> dict:
    asset_id = _clean(payload.get("asset_id"), 80)
    buyer = _clean(payload.get("buyer"), 180)
    terms = _clean(payload.get("terms"), 3000)
    if not asset_id or not buyer or not terms:
        raise ValueError("Asset, prospective buyer and draft terms are required.")
    with connect() as db:
        asset = db.execute("SELECT * FROM code_assets WHERE id=?", (asset_id,)).fetchone()
        if asset is None:
            raise LookupError("Code asset not found.")
        if asset["ownership_status"].casefold() not in {"verified", "owner_confirmed"}:
            raise ValueError("Licensing is blocked until ownership is verified.")
        if asset["dependency_review"].casefold() not in {"passed", "reviewed_clear"}:
            raise ValueError("Licensing is blocked until third-party dependency review is clear.")
        offer = {
            "id": str(uuid4()), "asset_id": asset_id, "buyer": buyer,
            "terms": terms, "status": "draft_pending_owner_approval",
            "created_at": now(), "updated_at": now(),
        }
        db.execute(
            """INSERT INTO license_offers
            (id,asset_id,buyer,terms,status,created_at,updated_at)
            VALUES (:id,:asset_id,:buyer,:terms,:status,:created_at,:updated_at)""",
            offer,
        )
        approval = {
            "id": str(uuid4()), "task_id": None,
            "action": "review_code_license_offer",
            "details": f"Review draft licensing offer {offer['id']} for asset {asset['name']} and prospective buyer {buyer}. No code or repository has been shared.",
            "status": "pending", "created_at": now(), "decided_at": None,
        }
        db.execute(
            """INSERT INTO approvals (id,task_id,action,details,status,created_at,decided_at)
            VALUES (:id,:task_id,:action,:details,:status,:created_at,:decided_at)""",
            approval,
        )
    return {**offer, "approval_id": approval["id"], "external_sharing": False}


def apply_expense_approval(approval_id: str, decision: str) -> None:
    """Mirror a completed owner decision onto the linked expense ledger row."""
    status = {"approved": "approved_for_manual_payment", "rejected": "rejected_by_owner"}.get(decision)
    if status is None:
        return
    with connect() as db:
        db.execute(
            "UPDATE business_records SET status=? WHERE approval_id=? AND record_type='expense'",
            (status, approval_id),
        )


def list_investors(limit: int = 300, business_id: str = "core") -> list[dict]:
    scope = _scope(business_id)
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM investor_contacts WHERE business_id=? ORDER BY created_at DESC LIMIT ?",
            (scope, max(1, min(limit, 500))),
        ).fetchall()
    return [dict(x) for x in rows]


def create_investor(payload: dict) -> dict:
    scope = _scope(payload.get("business_id", "core"))
    name = _clean(payload.get("name"), 180)
    if not name:
        raise ValueError("Investor name is required.")
    stage = _clean(payload.get("stage", "prospect"), 40).lower()
    if stage not in {"prospect", "contacted", "interested", "due_diligence", "committed", "declined"}:
        raise ValueError("Unsupported investor stage.")
    item = {
        "id": str(uuid4()), "business_id": scope, "name": name,
        "organization": _clean(payload.get("organization"), 180),
        "contact": _clean(payload.get("contact"), 200),
        "stage": stage, "notes": _clean(payload.get("notes"), 2000),
        "created_at": now(), "updated_at": now(),
    }
    with connect() as db:
        db.execute(
            """INSERT INTO investor_contacts
            (id,business_id,name,organization,contact,stage,notes,created_at,updated_at)
            VALUES (:id,:business_id,:name,:organization,:contact,:stage,:notes,:created_at,:updated_at)""",
            item,
        )
    return item
