"""Read-only repository asset inventory and conservative token-volume audit."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from ai_os.db import connect

MAX_TREE_ENTRIES = 5000
MAX_SOURCE_FILES = 120
MAX_SOURCE_BYTES = 2_000_000
MAX_HISTORY_COMMITS = 30
SKIP_PARTS = {
    ".git", ".venv", "venv", "node_modules", "vendor", "dist", "build",
    "__pycache__", ".next", "coverage", "target", "generated", "third_party",
}
SKIP_NAMES = {
    ".env", ".env.local", ".env.production", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock",
    "go.sum", "composer.lock",
}
SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt",
    ".go", ".rs", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".hpp",
    ".swift", ".sh", ".sql", ".html", ".css", ".scss", ".vue", ".svelte",
    ".md", ".toml", ".yaml", ".yml", ".json", ".xml",
}
MANIFEST_NAMES = {
    "requirements.txt", "pyproject.toml", "package.json", "go.mod",
    "Cargo.toml", "Gemfile", "composer.json",
}
SECRET_NAME = re.compile(r"(^|/)(\.env($|\.)|.*\.(pem|key|p12|pfx)$|id_rsa$)", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_parts(value: str) -> tuple[str, str, str]:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError("Only public GitHub repository HTTPS URLs are supported.")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2 or parts[0] in {".", ".."} or parts[1] in {".", ".."}:
        raise ValueError("Provide a canonical https://github.com/owner/repository URL.")
    owner, repo = parts[0], parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo):
        raise ValueError("Repository URL contains an invalid owner or repository name.")
    repo = repo.removesuffix(".git")
    return owner, repo, f"https://github.com/{owner}/{repo}"


def _github_json(path: str) -> dict | list:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AIOS-Code-Asset-Auditor/1.0"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request("https://api.github.com" + path, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(3_000_001)
        if len(raw) > 3_000_000:
            raise RuntimeError("GitHub response exceeded the 3 MB safety limit.")
        return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise LookupError("Repository or requested GitHub resource was not found or is not accessible.") from exc
        if exc.code in (403, 429):
            raise RuntimeError("GitHub API rate limit or access restriction; retry after the limit resets.") from exc
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"GitHub read failed: {exc}") from exc


def _raw_text(owner: str, repo: str, branch: str, path: str, max_bytes: int = 200_000) -> str:
    safe_path = "/".join(quote(part, safe="") for part in path.split("/"))
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{quote(branch, safe='')}/{safe_path}"
    request = Request(url, headers={"User-Agent": "AIOS-Code-Asset-Auditor/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return ""
        return raw.decode("utf-8")
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, OSError):
        return ""


def _eligible_source(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    lowered = path.lower()
    if name in SKIP_NAMES or SECRET_NAME.search(path):
        return False
    if any(part.lower() in SKIP_PARTS for part in path.split("/")):
        return False
    if lowered.endswith((".min.js", ".map", ".lock")):
        return False
    return "." + name.rsplit(".", 1)[-1].lower() in SOURCE_SUFFIXES if "." in name else False


def _dependency_summary(manifests: list[dict]) -> list[dict]:
    results = []
    for item in manifests:
        path, content = item["path"], item["content"]
        ecosystem = "unknown"
        names: list[str] = []
        if path.endswith("requirements.txt"):
            ecosystem = "python"
            names = [line.strip().split(";")[0].split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip()
                     for line in content.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        elif path.endswith("pyproject.toml"):
            ecosystem = "python"
            names = re.findall(r'(?m)^([A-Za-z0-9_.-]+)\s*=\s*["\']', content)
        elif path.endswith("package.json"):
            ecosystem = "npm"
            try:
                data = json.loads(content)
                names = list((data.get("dependencies") or {}).keys()) + list((data.get("devDependencies") or {}).keys())
            except json.JSONDecodeError:
                names = []
        elif path.endswith("go.mod"):
            ecosystem = "go"
            names = re.findall(r'(?m)^\s*([A-Za-z0-9._/-]+)\s+v[0-9]', content)
        elif path.endswith("Cargo.toml"):
            ecosystem = "rust"
            names = re.findall(r'(?m)^([A-Za-z0-9_-]+)\s*=', content)
        elif path.endswith("composer.json"):
            ecosystem = "composer"
            try:
                data = json.loads(content)
                names = list((data.get("require") or {}).keys()) + list((data.get("require-dev") or {}).keys())
            except json.JSONDecodeError:
                names = []
        results.append({
            "manifest": path, "ecosystem": ecosystem,
            "dependency_names": sorted(set(n for n in names if n and n.lower() not in {"python", "php"}))[:300],
            "declared_license": "not-resolved",
            "note": "Manifest inventory only; package licenses and transitive dependencies require separate verification."
        })
    return results


def scan_repository(repository_url: str) -> dict:
    owner, repo, canonical = _repo_parts(repository_url)
    metadata = _github_json(f"/repos/{quote(owner)}/{quote(repo)}")
    if metadata.get("private"):
        raise ValueError("Private repository scanning is not enabled in this read-only public-repository phase.")
    branch = metadata.get("default_branch") or "main"
    tree_doc = _github_json(f"/repos/{quote(owner)}/{quote(repo)}/git/trees/{quote(branch, safe='')}?recursive=1")
    entries = tree_doc.get("tree", []) if isinstance(tree_doc, dict) else []
    if not isinstance(entries, list):
        entries = []
    truncated = bool(tree_doc.get("truncated")) if isinstance(tree_doc, dict) else False
    entries = entries[:MAX_TREE_ENTRIES]
    file_entries = [x for x in entries if isinstance(x, dict) and x.get("type") == "blob" and isinstance(x.get("path"), str)]
    manifest_paths = [x["path"] for x in file_entries if x["path"].rsplit("/", 1)[-1] in MANIFEST_NAMES]
    license_paths = [x["path"] for x in file_entries if re.match(r"(?i)(^|/)(license|copying)(\.|$)", x["path"].rsplit("/", 1)[-1])]
    manifests = []
    for path in manifest_paths[:20]:
        content = _raw_text(owner, repo, branch, path)
        if content:
            manifests.append({"path": path, "content": content})
    license_evidence = []
    for path in license_paths[:5]:
        content = _raw_text(owner, repo, branch, path, 50_000)
        if content:
            license_evidence.append({"path": path, "detected": True, "bytes": len(content.encode("utf-8"))})
    license_meta = metadata.get("license") or {}
    declared_license = license_meta.get("spdx_id") or license_meta.get("name") or "unknown"

    source_paths = [x["path"] for x in file_entries if _eligible_source(x["path"])][:MAX_SOURCE_FILES]
    total_source_bytes = 0
    total_source_chars = 0
    scanned_source_files = 0
    for path in source_paths:
        if total_source_bytes >= MAX_SOURCE_BYTES:
            break
        content = _raw_text(owner, repo, branch, path, min(150_000, MAX_SOURCE_BYTES - total_source_bytes))
        if not content:
            continue
        size = len(content.encode("utf-8"))
        total_source_bytes += size
        total_source_chars += len(content)
        scanned_source_files += 1

    history = _github_json(f"/repos/{quote(owner)}/{quote(repo)}/commits?per_page={MAX_HISTORY_COMMITS}")
    commits = history if isinstance(history, list) else []
    snapshot_commit_sha = (commits[0].get("sha") or "") if commits and isinstance(commits[0], dict) else ""
    additions = deletions = 0
    history_stats_complete = True
    for commit in commits[:MAX_HISTORY_COMMITS]:
        sha = (commit.get("sha") or "") if isinstance(commit, dict) else ""
        if not sha:
            continue
        detail = _github_json(f"/repos/{quote(owner)}/{quote(repo)}/commits/{quote(sha)}")
        stats = detail.get("stats") or {}
        if not stats:
            history_stats_complete = False
        additions += int(stats.get("additions") or 0)
        deletions += int(stats.get("deletions") or 0)
    history_estimated_chars = (additions + deletions) * 80
    token_metrics = {
        "source_code": {
            "estimated_tokens": round(total_source_chars / 4),
            "method": "UTF-8 decoded source character count divided by 4",
            "exact": False,
            "files_scanned": scanned_source_files,
            "bytes_scanned": total_source_bytes,
            "files_considered_limit": MAX_SOURCE_FILES,
            "byte_limit": MAX_SOURCE_BYTES,
            "confidence": "low; tokenizer-independent rough estimate",
        },
        "git_history": {
            "estimated_tokens": round(history_estimated_chars / 4),
            "method": "GitHub commit additions plus deletions multiplied by 80 assumed characters per changed line, then divided by 4",
            "exact": False,
            "commits_sampled": len(commits[:MAX_HISTORY_COMMITS]),
            "additions": additions,
            "deletions": deletions,
            "stats_complete": history_stats_complete,
            "confidence": "low; sampled commit stats and assumed average line length",
        },
    }
    now = _now()
    asset_id = str(uuid4())
    record = {
        "id": asset_id, "repository_url": canonical,
        "full_name": metadata.get("full_name") or f"{owner}/{repo}",
        "description": metadata.get("description") or "",
        "visibility": "public", "default_branch": branch,
        "snapshot_commit_sha": snapshot_commit_sha,
        "provenance": "unknown",
        "ownership_status": "unverified",
        "license": declared_license,
        "license_files": license_evidence,
        "dependencies": _dependency_summary(manifests),
        "file_count": len(file_entries),
        "tree_truncated": truncated or len(file_entries) >= MAX_TREE_ENTRIES,
        "token_metrics": token_metrics,
        "readiness": "needs-evidence",
        "risk_flags": [
            "Repository visibility does not establish company ownership.",
            "Contributor rights and third-party dependency licenses are not verified.",
            "Token volumes are rough estimates, not exact model-tokenizer measurements.",
        ],
        "scanned_at": now,
        "side_effects": "read-only GitHub metadata and file reads; no code execution, sharing, publishing, token creation, licensing, or payments",
    }
    with connect() as db:
        db.execute(
            """INSERT INTO code_assets
            (id,repository_url,full_name,description,visibility,default_branch,snapshot_commit_sha,
             provenance,ownership_status,license,license_files_json,dependencies_json,file_count,
             tree_truncated,token_metrics_json,readiness,risk_flags_json,scanned_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(repository_url) DO UPDATE SET
             full_name=excluded.full_name,description=excluded.description,visibility=excluded.visibility,
             default_branch=excluded.default_branch,snapshot_commit_sha=excluded.snapshot_commit_sha,
             license=excluded.license,license_files_json=excluded.license_files_json,
             dependencies_json=excluded.dependencies_json,file_count=excluded.file_count,
             tree_truncated=excluded.tree_truncated,token_metrics_json=excluded.token_metrics_json,
             risk_flags_json=excluded.risk_flags_json,scanned_at=excluded.scanned_at""",
            (record["id"], canonical, record["full_name"], record["description"], record["visibility"],
             branch, record["snapshot_commit_sha"], "unknown", "unverified", declared_license,
             json.dumps(license_evidence), json.dumps(record["dependencies"]), len(file_entries),
             int(record["tree_truncated"]), json.dumps(token_metrics), "needs-evidence",
             json.dumps(record["risk_flags"]), now)
        )
        saved = db.execute("SELECT * FROM code_assets WHERE repository_url=?", (canonical,)).fetchone()
    return _decode_asset(saved)


def _decode_asset(row) -> dict:
    item = dict(row)
    for key in ("license_files_json", "dependencies_json", "token_metrics_json", "risk_flags_json"):
        item[key.removesuffix("_json")] = json.loads(item.pop(key) or "[]")
    item["tree_truncated"] = bool(item["tree_truncated"])
    return item


def list_assets() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM code_assets ORDER BY scanned_at DESC LIMIT 200").fetchall()
    return [_decode_asset(row) for row in rows]


def get_asset(asset_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM code_assets WHERE id=?", (asset_id,)).fetchone()
    return _decode_asset(row) if row else None
