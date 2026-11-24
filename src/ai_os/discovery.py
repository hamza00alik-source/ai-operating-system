"""Supervised GitHub repository discovery and conservative evaluation."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
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


def github_api_status() -> dict:
    """Perform a small live GitHub API check without exposing credentials."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AIOS-Research-Discovery"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request("https://api.github.com/rate_limit", headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        resources = payload.get("resources", {})
        core = resources.get("core", {})
        search = resources.get("search", {})
        return {
            "connected": True,
            "authentication": "authenticated" if token else "public-unauthenticated",
            "token_configured": bool(token),
            "core_limit": core.get("limit"),
            "core_remaining": core.get("remaining"),
            "search_limit": search.get("limit"),
            "search_remaining": search.get("remaining"),
            "checked_at": now(),
            "error": None,
        }
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "connected": False,
            "authentication": "authenticated" if token else "public-unauthenticated",
            "token_configured": bool(token),
            "core_limit": None,
            "core_remaining": None,
            "search_limit": None,
            "search_remaining": None,
            "checked_at": now(),
            "error": str(exc)[:300],
        }



FREE_API_CATALOG_SOURCE = {
    "source_id": "idoY12-awesome-free-ai-apis",
    "repository": "IdoY12/awesome-free-ai-apis",
    "license": "CC0-1.0",
    "source_url": "https://github.com/IdoY12/awesome-free-ai-apis",
    "data_url": "https://raw.githubusercontent.com/IdoY12/awesome-free-ai-apis/main/data/providers.json",
    "status_url": "https://raw.githubusercontent.com/IdoY12/awesome-free-ai-apis/main/data/status.json",
    "assessment": "Primary-source-linked structured catalog; daily probes; provider terms still require independent review.",
}

SECONDARY_CATALOG_ASSESSMENTS = [
    {
        "repository": "bradAGI/awesome-free-inference",
        "license": "MIT",
        "decision": "secondary-only",
        "reason": "Useful manual README and model directory, but its visible verification badge says March 2026 and the fetched repository has no machine-readable provider dataset. Do not treat its rate limits or free-tier claims as current without provider-source checks.",
        "url": "https://github.com/bradAGI/awesome-free-inference",
    },
    {
        "repository": "dhaulagani/awesome-free-ai-apis",
        "license": "not-found",
        "decision": "excluded-pending-evidence",
        "reason": "README makes uptime, latency, quota, and production-readiness claims, but a repository LICENSE file was not found and the fetched README does not expose a structured provider dataset with linked primary-source evidence per provider.",
        "url": "https://github.com/dhaulagani/awesome-free-ai-apis",
    },
]


def _safe_https_url(value: object) -> str:
    text = str(value or "").strip()
    return text[:500] if text.startswith("https://") else ""


def _fetch_catalog_json(url: str, max_bytes: int = 2_000_000) -> dict:
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "AIOS-Free-API-Catalog/1.0",
    })
    with urlopen(request, timeout=20) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise RuntimeError("Free API catalog exceeded the safe 2 MB import limit.")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Free API catalog returned an unexpected document shape.")
    return payload


def sync_free_api_catalog() -> dict:
    """Import public catalog evidence only; never connect or call a provider API."""
    source = FREE_API_CATALOG_SOURCE
    catalog = _fetch_catalog_json(source["data_url"])
    status_doc = _fetch_catalog_json(source["status_url"])
    providers = catalog.get("providers")
    if not isinstance(providers, list) or not providers or len(providers) > 500:
        raise RuntimeError("Free API catalog provider list failed validation.")
    status_results = status_doc.get("results") if isinstance(status_doc.get("results"), dict) else {}
    synced_at = now()
    imported = 0
    with connect() as db:
        for item in providers:
            if not isinstance(item, dict):
                continue
            provider_id = str(item.get("id") or "").strip()[:120]
            name = str(item.get("name") or "").strip()[:200]
            category = str(item.get("category") or "unknown").strip()[:80]
            if not provider_id or not name:
                continue
            provider_status = status_results.get(provider_id, {})
            db.execute(
                """INSERT INTO provider_catalog_entries
                (source_id,provider_id,name,category,website,api_key_url,base_url,
                 free_tier_json,policy_json,confidence,last_verified,probe_json,
                 status_json,sources_json,source_url,synced_at,review_state)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending')
                ON CONFLICT(source_id,provider_id) DO UPDATE SET
                 name=excluded.name,category=excluded.category,website=excluded.website,
                 api_key_url=excluded.api_key_url,base_url=excluded.base_url,
                 free_tier_json=excluded.free_tier_json,policy_json=excluded.policy_json,
                 confidence=excluded.confidence,last_verified=excluded.last_verified,
                 probe_json=excluded.probe_json,status_json=excluded.status_json,sources_json=excluded.sources_json,
                 source_url=excluded.source_url,synced_at=excluded.synced_at""",
                (
                    source["source_id"], provider_id, name, category,
                    _safe_https_url(item.get("website")),
                    _safe_https_url(item.get("api_key_url")),
                    _safe_https_url(item.get("base_url")),
                    json.dumps(item.get("free_tier") or {}, ensure_ascii=False),
                    json.dumps(item.get("policy") or {}, ensure_ascii=False),
                    str(item.get("confidence") or "unknown")[:40],
                    str(item.get("last_verified") or "")[:40] or None,
                    json.dumps({
                        "type": str((item.get("probe") or {}).get("type") or "")[:40],
                        "docs_url": _safe_https_url((item.get("probe") or {}).get("docs_url")),
                    }, ensure_ascii=False),
                    json.dumps(provider_status or {}, ensure_ascii=False),
                    json.dumps([
                        { "title": str(source_item.get("title") or "")[:200],
                          "url": _safe_https_url(source_item.get("url")),
                          "accessed": str(source_item.get("accessed") or "")[:40] }
                        for source_item in (item.get("sources") or [])
                        if isinstance(source_item, dict) and _safe_https_url(source_item.get("url"))
                    ][:20], ensure_ascii=False),
                    source["source_url"], synced_at,
                ),
            )
            imported += 1
    summary = status_doc.get("summary") if isinstance(status_doc.get("summary"), dict) else {}
    return {
        "source": source["repository"],
        "license": source["license"],
        "imported": imported,
        "catalog_review_date": (catalog.get("meta") or {}).get("last_full_review"),
        "status_checked_at": summary.get("checked_at"),
        "status_summary": {
            "providers": summary.get("providers"),
            "live_up": summary.get("live_up"),
            "live_down": summary.get("live_down"),
            "docs_broken": summary.get("docs_broken"),
        },
        "synced_at": synced_at,
        "secondary_sources": SECONDARY_CATALOG_ASSESSMENTS,
        "important": "Catalog evidence only. No provider credentials were saved, no inference APIs were called, and no provider was enabled.",
    }


def _evidence_freshness(last_verified: str | None, sources: list[dict] | None = None, *, max_age_days: int = 30) -> dict:
    """Classify evidence age conservatively; this is not a live provider test."""
    def parse(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    verified_date = parse(last_verified)
    basis = "catalog last_verified date; not a live provider test"
    evidence_date = verified_date
    if evidence_date is None:
        source_dates = [
            parsed for source in (sources or []) if isinstance(source, dict)
            if (parsed := parse(source.get("accessed"))) is not None
        ]
        evidence_date = max(source_dates) if source_dates else None
        basis = "source accessed date only; not a provider verification or live test"
    if evidence_date is None:
        return {"state": "unknown", "age_days": None, "max_age_days": max_age_days,
                "basis": "no usable verification or source-access date"}
    age_days = max(0, (datetime.now(timezone.utc).date() - evidence_date.date()).days)
    return {"state": "stale" if age_days > max_age_days else "recent",
            "age_days": age_days, "max_age_days": max_age_days, "basis": basis}



def list_free_api_catalog(category: str | None = None) -> dict:
    with connect() as db:
        query = "SELECT * FROM provider_catalog_entries WHERE source_id=?"
        params: list = [FREE_API_CATALOG_SOURCE["source_id"]]
        if category:
            query += " AND category=?"
            params.append(category)
        query += " ORDER BY category,name"
        rows = db.execute(query, params).fetchall()
    providers = []
    for row in rows:
        item = dict(row)
        for field in ("free_tier_json", "policy_json", "probe_json", "status_json", "sources_json"):
            item[field.removesuffix("_json")] = json.loads(item.pop(field) or "{}")
        item["evidence_freshness"] = _evidence_freshness(item.get("last_verified"), item.get("sources"))
        item["routing_eligible"] = False
        item["routing_note"] = "Research catalog entries never enable or authorize provider routing."
        providers.append(item)
    freshness_counts = {
        state: sum(1 for item in providers if item["evidence_freshness"]["state"] == state)
        for state in ("recent", "stale", "unknown")
    }
    return {
        "source": FREE_API_CATALOG_SOURCE,
        "provider_count": len(providers),
        "evidence_freshness": {"max_age_days": 30, "counts": freshness_counts},
        "providers": providers,
        "secondary_sources": SECONDARY_CATALOG_ASSESSMENTS,
        "safety": "Unverified listings are research leads only; owner approval and a live provider test are required before credentials can be enabled.",
    }


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
                "stars": repo.get("stargazers_count", 0), "language": repo.get("language"),
                "fork": bool(repo.get("fork", False)), "updated_at": repo.get("updated_at"),
                "open_issues": repo.get("open_issues_count"), "default_branch": repo.get("default_branch"),
                "topics": repo.get("topics") or [],
                "cost": "unknown", "security": "not-tested",
                "commercial_use": "not-verified", "reason": reason}
    return {"canonical_url": url, "full_name": repo.get("full_name", ""),
            "description": repo.get("description") or "", "category": category,
            "license": license_name, "maintenance": maintenance,
            "status": status, "stars": int(repo.get("stargazers_count") or 0),
            "discovered_at": now(), "evidence": evidence}

def _github_search(query: str) -> list[dict]:
    params = urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 20})
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

def _ensure_scan_lease_columns(db) -> None:
    columns = {row['name'] for row in db.execute('PRAGMA table_info(discovery_scans)')}
    for name in ('lease_owner', 'lease_expires_at'):
        if name not in columns:
            db.execute('ALTER TABLE discovery_scans ADD COLUMN ' + name + ' TEXT')
    db.execute('CREATE INDEX IF NOT EXISTS idx_discovery_scans_lease ON discovery_scans(status, lease_expires_at)')


def claim_next_scan(worker_id: str, lease_seconds: int = 180) -> dict | None:
    if not worker_id or not worker_id.strip():
        raise ValueError('A non-empty worker identity is required.')
    duration = max(60, min(int(lease_seconds), 3600))
    current = datetime.now(timezone.utc)
    expires = datetime.fromtimestamp(current.timestamp() + duration, timezone.utc).isoformat()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _ensure_scan_lease_columns(db)
        row = db.execute("SELECT id FROM discovery_scans WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return None
        changed = db.execute("UPDATE discovery_scans SET status='running',started_at=?,lease_owner=?,lease_expires_at=? WHERE id=? AND status='queued'", (current.isoformat(), worker_id, expires, row['id'])).rowcount
        if changed != 1:
            return None
        claimed = db.execute('SELECT * FROM discovery_scans WHERE id=?', (row['id'],)).fetchone()
    return dict(claimed)


def claim_scan_by_id(scan_id: str, worker_id: str) -> dict | None:
    current = now()
    expires = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + 180, timezone.utc).isoformat()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _ensure_scan_lease_columns(db)
        changed = db.execute("UPDATE discovery_scans SET status='running',started_at=?,lease_owner=?,lease_expires_at=? WHERE id=? AND status='queued'", (current, worker_id, expires, scan_id)).rowcount
        if changed != 1:
            return None
        row = db.execute('SELECT * FROM discovery_scans WHERE id=?', (scan_id,)).fetchone()
    return dict(row)


def renew_scan_lease(scan_id: str, worker_id: str, lease_seconds: int = 180) -> bool:
    duration = max(60, min(int(lease_seconds), 3600))
    expires = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + duration, timezone.utc).isoformat()
    with connect() as db:
        _ensure_scan_lease_columns(db)
        changed = db.execute("UPDATE discovery_scans SET lease_expires_at=? WHERE id=? AND status='running' AND lease_owner=? AND lease_expires_at>?", (expires, scan_id, worker_id, now())).rowcount
    return changed == 1


def recover_interrupted_scans() -> int:
    current = now()
    with connect() as db:
        _ensure_scan_lease_columns(db)
        rows = db.execute("SELECT id FROM discovery_scans WHERE status='running' AND (lease_expires_at IS NULL OR lease_expires_at<=?)", (current,)).fetchall()
        recovered = 0
        for row in rows:
            recovered += db.execute("UPDATE discovery_scans SET status='failed',finished_at=?,error=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND status='running' AND (lease_expires_at IS NULL OR lease_expires_at<=?)", (current, 'Discovery scan interrupted; owner review is required before retry.', row['id'], current)).rowcount
    return recovered


def _assert_scan_lease(scan_id: str, worker_id: str) -> None:
    with connect() as db:
        row = db.execute("SELECT 1 FROM discovery_scans WHERE id=? AND status='running' AND lease_owner=? AND lease_expires_at>?", (scan_id, worker_id, now())).fetchone()
    if row is None:
        raise RuntimeError('Discovery worker no longer owns a live scan lease.')


def run_scan(scan_id: str, worker_id: str | None = None, *, already_claimed: bool = False) -> dict:
    worker_id = worker_id or ('discovery-' + str(uuid4()))
    row = None
    if already_claimed:
        _assert_scan_lease(scan_id, worker_id)
        with connect() as db:
            row = db.execute('SELECT * FROM discovery_scans WHERE id=?', (scan_id,)).fetchone()
    else:
        row = claim_scan_by_id(scan_id, worker_id)
    if row is None:
        raise LookupError('Discovery scan not found or no longer claimable.')
    count = 0
    stop_heartbeat = threading.Event()
    def heartbeat() -> None:
        while not stop_heartbeat.wait(30):
            if not renew_scan_lease(scan_id, worker_id):
                return
    heartbeat_thread = threading.Thread(target=heartbeat, name='aios-discovery-lease-' + scan_id[:8], daemon=True)
    heartbeat_thread.start()
    try:
        for category in json.loads(row['categories']):
            _assert_scan_lease(scan_id, worker_id)
            repositories = _github_search(CATEGORIES[category])
            _assert_scan_lease(scan_id, worker_id)
            for repo in repositories:
                candidate = evaluate_repository(repo, category)
                if not candidate['canonical_url']:
                    continue
                with connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    lease = db.execute("SELECT 1 FROM discovery_scans WHERE id=? AND status='running' AND lease_owner=? AND lease_expires_at>?", (scan_id, worker_id, now())).fetchone()
                    if lease is None:
                        raise RuntimeError('Discovery worker lost its lease before saving a candidate.')
                    db.execute('''INSERT INTO discovery_candidates
                      (canonical_url,full_name,description,category,license,maintenance,status,stars,discovered_at,evidence)
                      VALUES (:canonical_url,:full_name,:description,:category,:license,:maintenance,:status,:stars,:discovered_at,:evidence)
                      ON CONFLICT(canonical_url) DO UPDATE SET description=excluded.description,license=excluded.license,
                      maintenance=excluded.maintenance,status=excluded.status,stars=excluded.stars,
                      discovered_at=excluded.discovered_at,evidence=excluded.evidence''',
                      {**candidate, 'evidence': json.dumps(candidate['evidence'])})
                count += 1
            time.sleep(1)
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute("UPDATE discovery_scans SET status='completed',finished_at=?,result_count=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND status='running' AND lease_owner=? AND lease_expires_at>?", (now(), count, scan_id, worker_id, now())).rowcount
            if changed != 1:
                raise RuntimeError('Discovery scan lease was lost before completion.')
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE discovery_scans SET status='failed',finished_at=?,result_count=?,error=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND status='running' AND lease_owner=? AND lease_expires_at>?", (now(), count, str(exc)[:1000], scan_id, worker_id, now()))
        raise
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=2)
    with connect() as db:
        result = db.execute('SELECT * FROM discovery_scans WHERE id=?', (scan_id,)).fetchone()
    return dict(result)


def run_pending_once(worker_id: str | None = None) -> bool:
    worker_id = worker_id or ('discovery-' + str(uuid4()))
    claimed = claim_next_scan(worker_id)
    if not claimed:
        return False
    run_scan(claimed['id'], worker_id, already_claimed=True)
    return True
