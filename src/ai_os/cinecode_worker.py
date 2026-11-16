"""Opt-in local Cinecode worker for the native AIOS queue.

This process is intentionally separate from the web service. It requires an
isolated host, pinned Cinecode checkout, separate Codex service identity and
explicit execution + billing gates. It never publishes or contacts customers.
"""
from __future__ import annotations

import json
import logging
import selectors
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from ai_os.cinecode import initialize_cinecode, _now, MAX_ARTIFACT_BYTES
from ai_os.db import connect

logger = logging.getLogger("ai_os.cinecode_worker")
STOP = False
MAX_RENDER_SECONDS = 3600
MAX_STORAGE_BYTES = 300 * 1024 * 1024
MIN_FREE_BYTES = 64 * 1024 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
POLL_SECONDS = 5


def _enabled() -> bool:
    return (
        os.getenv("AI_OS_CINECODE_EXECUTION_ENABLED", "").lower() == "true"
        and os.getenv("AI_OS_CINECODE_BILLING_CONFIRMED", "").lower() == "true"
    )


def _source_checkout() -> Path:
    source = Path(os.environ.get("CINECODE_SOURCE_DIR", "")).resolve()
    expected = os.environ.get("CINECODE_SOURCE_COMMIT", "").strip()
    if not expected or not source.is_dir() or not (source / ".git").exists():
        raise RuntimeError("A pre-provisioned Cinecode Git checkout and CINECODE_SOURCE_COMMIT are required.")
    actual = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    if actual != expected or dirty:
        raise RuntimeError("Cinecode source must be clean and match CINECODE_SOURCE_COMMIT exactly.")
    return source


def _worker_environment() -> dict[str, str]:
    codex_home = Path(os.environ.get("CODEX_HOME", "")).resolve()
    if not codex_home.is_dir():
        raise RuntimeError("CODEX_HOME must point to the dedicated Codex service identity directory.")
    path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    return {
        "PATH": path,
        "HOME": os.environ.get("HOME", str(codex_home.parent)),
        "CODEX_HOME": str(codex_home),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }


def _claim(worker_id: str):
    initialize_cinecode()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM cinecode_jobs WHERE status='approved' AND cancel_requested=0 ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        now = _now()
        updated = db.execute(
            """UPDATE cinecode_jobs SET status='running',worker_id=?,started_at=?,updated_at=?,
               progress='Preparing isolated render workspace'
               WHERE id=? AND status='approved' AND cancel_requested=0""",
            (worker_id, now, now, row["id"]),
        )

        if updated.rowcount != 1:
            return None
    return dict(row)


def _set_progress(job_id: str, message: str) -> None:
    with connect() as db:
        db.execute(
            "UPDATE cinecode_jobs SET progress=?,updated_at=? WHERE id=? AND status='running'",
            (message[:500], _now(), job_id),
        )

def _cancelled(job_id: str) -> bool:
    with connect() as db:
        row = db.execute(
            "SELECT cancel_requested FROM cinecode_jobs WHERE id=?", (job_id,)
        ).fetchone()
    return row is None or bool(row["cancel_requested"])


def _finish(job_id: str, *, status: str, error: str | None = None,
            artifact_path: str | None = None, digest: str | None = None,
            size: int | None = None, report_path: str | None = None) -> None:
    now = _now()
    progress = {
        "succeeded": "MP4 validated and stored privately",
        "failed": "Render failed; inspect the private worker logs",
        "cancelled": "Cancelled by owner",
    }[status]
    with connect() as db:
        db.execute(
            """UPDATE cinecode_jobs SET status=?,error=?,artifact_path=?,artifact_sha256=?,
               artifact_bytes=?,report_path=?,finished_at=?,updated_at=?,progress=?
               WHERE id=?""",
            (status, error[:2000] if error else None, artifact_path, digest, size,
             report_path, now, now, progress, job_id),
        )

def _run_render(job: dict, source: Path, env: dict[str, str]) -> None:
    job_id = job["id"]
    storage = Path(os.getenv("AI_OS_CINECODE_STORAGE_DIR", "/data/cinecode")).resolve()
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(storage, 0o700)
    with tempfile.TemporaryDirectory(prefix="aios-cinecode-") as temp:
        root = Path(temp).resolve()
        kit = root / "cinecode-kit"
        project = root / "film-project"
        shutil.copytree(source, kit, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "node_modules"))
        project.mkdir(mode=0o700)
        prompt = (
            "You are rendering one owner-approved film brief using the Cinecode kit in ./cinecode-kit. "
            "Read the kit's AGENTS.md and SKILL.md and follow them. Work only in ./film-project. "
            "Do not access credentials, modify the kit, publish, upload to third parties, or contact anyone. "
            "Use the requested mode and music selection. Create a complete MP4 at "
            "./film-project/output/final.mp4 and a concise production report at "
            "./film-project/production-report.md. The report must list scenes, assets, render settings, "
            "known limitations, and any source/licensing notes. Do not invent source licenses. "
            "If the kit cannot complete the render locally, stop and explain the blocker in the report.\n\n"
            f"MODE: {job['mode']}\nMUSIC: {job['music_source']}\nBRIEF:\n{job['brief']}"
        )
        last_message = root / "codex-last-message.txt"
        command = [
            "codex", "exec", "--sandbox", "workspace-write", "--ignore-user-config",
            "--ephemeral", "--json", "--output-last-message", str(last_message),
            "--skip-git-repo-check", "--cd", str(root), prompt,
        ]
        _set_progress(job_id, "Rendering locally with the isolated Codex service identity")
        process = subprocess.Popen(
            command, cwd=root, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=False, bufsize=0,
        )
        started = time.monotonic()
        output_lines: list[str] = []
        selector = selectors.DefaultSelector()
        if process.stdout is not None:
            selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while process.poll() is None:
                if _cancelled(job_id):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    _finish(job_id, status="cancelled")
                    return
                if time.monotonic() - started > MAX_RENDER_SECONDS:
                    process.kill()
                    _finish(job_id, status="failed", error="Render exceeded the one-hour worker limit.")
                    return
                for key, _ in selector.select(timeout=0.5):
                    chunk = key.fileobj.readline()
                    if chunk:
                        output_lines.append(chunk.decode("utf-8", errors="replace").rstrip()[:2000])
                        if len(output_lines) > 500:
                            output_lines = output_lines[-500:]
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        if process.returncode != 0:
            raise RuntimeError("Codex render process failed: " + "\n".join(output_lines[-20:]))
        mp4 = project / "output" / "final.mp4"
        report = project / "production-report.md"
        project_root = project.resolve()
        if (not mp4.is_file() or not report.is_file()
                or mp4.is_symlink() or report.is_symlink()
                or project_root not in mp4.resolve().parents
                or project_root not in report.resolve().parents):
            raise RuntimeError("Cinecode must produce regular in-workspace MP4 and report files.")
        size = mp4.stat().st_size
        report_size = report.stat().st_size
        if size <= 0 or size > MAX_ARTIFACT_BYTES:
            raise RuntimeError("Rendered MP4 is empty or exceeds the 250 MiB per-file limit.")
        if report_size <= 0 or report_size > MAX_REPORT_BYTES:
            raise RuntimeError("Production report is empty or exceeds the 2 MiB limit.")
        existing_bytes = sum(p.stat().st_size for p in storage.iterdir() if p.is_file() and not p.is_symlink())
        if existing_bytes + size + report_size > MAX_STORAGE_BYTES:
            raise RuntimeError("Private Cinecode storage would exceed its 300 MiB aggregate limit.")
        if shutil.disk_usage(storage).free - size - report_size < MIN_FREE_BYTES:
            raise RuntimeError("Render artifact storage would consume the 64 MiB free-space reserve.")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type,width,height",
             "-show_entries", "format=duration", "-of", "json", str(mp4)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        metadata = json.loads(probe.stdout)
        duration = float(metadata.get("format", {}).get("duration") or 0)
        if not metadata.get("streams") or duration <= 0:
            raise RuntimeError("ffprobe could not verify a video stream and positive duration.")
        target = storage / f"{job_id}.mp4"
        report_target = storage / f"{job_id}.production-report.md"
        shutil.copyfile(mp4, target)
        shutil.copyfile(report, report_target)
        os.chmod(target, 0o600)
        os.chmod(report_target, 0o600)
        import hashlib
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        _finish(job_id, status="succeeded", artifact_path=str(target),
                digest=digest, size=size, report_path=str(report_target))


def run_once(worker_id: str | None = None) -> bool:
    if not _enabled():
        raise RuntimeError("Cinecode worker is disabled; both execution and billing confirmation gates must be true.")
    source = _source_checkout()
    env = _worker_environment()
    job = _claim(worker_id or str(uuid.uuid4()))
    if job is None:
        return False
    try:
        _run_render(job, source, env)
    except Exception as exc:
        logger.exception("Cinecode job %s failed", job["id"])
        _finish(job["id"], status="failed", error=str(exc))
    return True


def _stop(_signum, _frame) -> None:
    global STOP
    STOP = True


def main() -> None:
    logging.basicConfig(level=os.getenv("AI_OS_LOG_LEVEL", "INFO"))
    if not _enabled():
        raise SystemExit("Cinecode worker is disabled. Explicitly set both AI_OS_CINECODE_EXECUTION_ENABLED=true and AI_OS_CINECODE_BILLING_CONFIRMED=true after reviewing the service identity and spend cap.")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    worker_id = os.getenv("AI_OS_CINECODE_WORKER_ID", str(uuid.uuid4()))
    while not STOP:
        try:
            if not run_once(worker_id):
                time.sleep(POLL_SECONDS)
        except Exception:
            logger.exception("Cinecode worker health check failed; retrying after backoff")
            time.sleep(30)


if __name__ == "__main__":
    main()
