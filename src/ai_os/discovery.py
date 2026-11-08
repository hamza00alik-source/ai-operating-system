"""Supervised GitHub repository discovery and conservative evaluation."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from ai_os.db import connect

CATEGORIES = {
    "agent-frameworks": "AI agent framework language:Python",
    "mcp-servers": "MCP server language:Python",
    "rag-storage": "RAG vector database language:Python",
    "self-hosted": "self hosted AI language:Python",
    "llm-tools": "LLM API tools language:Python",
}

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_scan(categories: list[str]) -> dict:
    selected = sorted(set(categories))
    if not selected or any(item not in CATEGORIES for item in selected):
        raise ValueError("Choose one or more supported discovery categories.")
    scan = {"id": str(uuid4()), "categories": json.dumps(selected),
            "status": "queued", "created_at": now(), "started_at": None,
            "finished_at": None, "result_count": 0, "error": None}
    with connect() as db:
        db.execute("""INSERT INTO discovery_scans
          (id,categories,status,created_at,started_at,finished_at,result_count,error)
          VALUES (:id,:categories,:status,:created_at,:started_at,:finished_at,:result_count,:error)""", scan)
    return scan

def list_scans() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM discovery_scans ORDER BY created_at DESC LIMIT 50").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["categories"] = json.loads(item["categories"])
        result.append(item)
    return result

def list_candidates() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM discovery_candidates ORDER BY discovered_at DESC LIMIT 200").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["evidence"] = json.loads(item["evidence"])
        result.append(item)
    return result

def evaluate_repository(repo: dict, category: str) -> dict:
    """Evaluate only facts present in GitHub metadata; unknowns stay unknown."""
    archived = bool(repo.get("archived", False))
    license_info = repo.get("license") or {}
    license_name = license_info.get("spdx_id") or license_info.get("name") or "unknown"
    pushed = repo.get("pushed_at")
    maintenance = "unknown"
    if pushed:
        try:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            maintenance = "recent" if age_days <= 180 else ("stale" if age_days > 730 else "moderate")
        except (TypeError, ValueError):
            pass
    if archived:
        status, reason = "needs-review", "Repository is archived."
    elif license_name.lower() == "unknown":
        status, reason = "needs-review", "License is not identified in repository metadata."
    elif maintenance == "stale":
        status, reason = "needs-review", "No recent push activity; inspect maintenance before use."
    else:
        status, reason = "discovered", "Metadata checks only; security, API terms, cost and commercial rights remain unverified."
    url = repo.get("html_url") or ""
    evidence = {"source": "GitHub repository metadata", "url": url,
                "checked_at": now(), "license": license_name,
                "archived": archived, "pushed_at": pushed,
                "stars": repo.get("stargazers_count", 0),
                "cost": "unknown", "security": "not-tested",
                "commercial_use": "not-verified", "reason": reason}
    return {"canonical_url": url, "full_name": repo.get("full_name", ""),
            "description": repo.get("description") or "", "category": category,
            "license": license_name, "maintenance": maintenance,
            "status": status, "stars": int(repo.get("stargazers_count") or 0),
            "discovered_at": now(), "evidence": evidence}

def _github_search(query: str) -> list[dict]:
    params = urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 10})
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AIOS-Research-Discovery"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/search/repositories?{params}", headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("items", [])
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise RuntimeError("GitHub rate limit or access restriction; retry later.") from exc
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"GitHub discovery request failed: {exc}") from exc

def run_scan(scan_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM discovery_scans WHERE id=?", (scan_id,)).fetchone()
        if row is None:
            raise LookupError("Discovery scan not found.")
        if row["status"] != "queued":
            raise ValueError("Only queued scans can be run.")
        db.execute("UPDATE discovery_scans SET status='running',started_at=? WHERE id=?", (now(), scan_id))
    count = 0
    try:
        categories = json.loads(row["categories"])
        for category in categories:
            for repo in _github_search(CATEGORIES[category]):
                candidate = evaluate_repository(repo, category)
                if not candidate["canonical_url"]:
                    continue
                with connect() as db:
                    db.execute("""INSERT INTO discovery_candidates
                      (canonical_url,full_name,description,category,license,maintenance,status,stars,discovered_at,evidence)
                      VALUES (:canonical_url,:full_name,:description,:category,:license,:maintenance,:status,:stars,:discovered_at,:evidence)
                      ON CONFLICT(canonical_url) DO UPDATE SET
                      description=excluded.description,license=excluded.license,
                      maintenance=excluded.maintenance,status=excluded.status,
                      stars=excluded.stars,discovered_at=excluded.discovered_at,evidence=excluded.evidence""",
                      {**candidate, "evidence": json.dumps(candidate["evidence"])})
                count += 1
            time.sleep(1)
        with connect() as db:
            db.execute("UPDATE discovery_scans SET status='completed',finished_at=?,result_count=? WHERE id=?", (now(), count, scan_id))
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE discovery_scans SET status='failed',finished_at=?,result_count=?,error=? WHERE id=?",
                       (now(), count, str(exc)[:1000], scan_id))
        raise
    with connect() as db:
        result = db.execute("SELECT * FROM discovery_scans WHERE id=?", (scan_id,)).fetchone()
    return dict(result)

def run_pending_once() -> bool:
    with connect() as db:
        row = db.execute("SELECT id FROM discovery_scans WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
    if not row:
        return False
    run_scan(row["id"])
    return True
