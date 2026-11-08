"""Supervised durable agent worker process.

The queue owns per-job retries and stale-lease recovery. This module adds a
process-level supervisor so transient scheduler/database errors do not terminate
the worker. A service manager should still restart the process after host failure.
"""
import json
import logging
import os
import time
import urllib.request
from urllib.parse import urlsplit
from uuid import uuid4
from threading import Event, Thread
from collections.abc import Callable

from ai_os.agent_runtime import schedule_ready_steps
from ai_os.model_adapter import get_model_status
from ai_os.worker import run_once
from ai_os.db import initialize_database
from ai_os.worker_control import get_worker_desired_state, heartbeat_worker
from ai_os.commerce import initialize_commerce_storage
from ai_os.control_plane import initialize_control_plane
from ai_os.credential_vault import initialize_credential_vault
from ai_os.agent_tools import register_builtin_agent_tools
from ai_os.wordpress_actions import register_wordpress_draft_adapter
from ai_os.woocommerce_actions import register_woocommerce_draft_adapter
from ai_os.mcp_broker import initialize_mcp_broker_storage

logger = logging.getLogger("ai_os.worker_service")


def run_worker_loop(
    *,
    worker_id: str,
    poll_seconds: int,
    stop_requested: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
    schedule: Callable[[], dict] = schedule_ready_steps,
    run: Callable[..., dict] = run_once,
    on_error: Callable[[Exception, int], None] | None = None,
    desired_state: Callable[[], str] = lambda: "running",
    heartbeat: Callable[[str, str, str | None], None] = lambda *_: None,
    heartbeat_interval_seconds: float = 20,
) -> None:
    """Run until stopped; exponentially back off after process-level failures."""
    delay = max(1, min(int(poll_seconds), 60))
    failure_count = 0
    heartbeat(worker_id, "starting", None)
    while not stop_requested():
        try:
            state = desired_state()
            if state != "running":
                heartbeat(worker_id, "paused" if state == "paused" else "stopped", None)
                sleep(delay)
                continue
            heartbeat(worker_id, "idle", None)
            scheduled = schedule()
            heartbeat_stop = Event()

            def maintain_runtime_heartbeat():
                interval = max(0.05, min(float(heartbeat_interval_seconds), 30.0))
                while not heartbeat_stop.wait(interval):
                    try:
                        heartbeat(worker_id, "working", None)
                    except Exception:
                        logger.exception("Runtime heartbeat refresh failed; control plane will mark this runtime stale if it persists.")

            heartbeat(worker_id, "working", None)
            heartbeat_thread = Thread(
                target=maintain_runtime_heartbeat,
                name=f"runtime-heartbeat-{worker_id[:12]}",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                result = run(worker_id=worker_id)
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=1)
            failure_count = 0
            heartbeat(worker_id, "working" if result.get("processed") else "idle",
                      (result.get("job") or {}).get("id"))
            if result.get("processed") or scheduled.get("scheduled"):
                continue
            sleep(delay)
        except Exception as exc:
            failure_count += 1
            backoff = min(60, delay * (2 ** min(failure_count - 1, 6)))
            heartbeat(worker_id, "error", None)
            if on_error is not None:
                on_error(exc, backoff)
            else:
                logger.exception(
                    "Worker loop recovered from process-level failure; retry in %ss",
                    backoff,
                )
            if not stop_requested():
                sleep(backoff)



def heartbeat_dispatch(worker_id: str, status: str, current_job_id: str | None) -> None:
    """Persist local worker health and optionally report to the authenticated control plane.

    Remote reporting is opt-in. If any remote credential setting is present, all
    three settings are required and HTTPS is mandatory except for localhost.
    """
    heartbeat_worker(worker_id, status, current_job_id)
    base_url = os.getenv("AI_OS_CONTROL_PLANE_URL", "").strip()
    runtime_id = os.getenv("AI_OS_RUNTIME_ID", "").strip()
    runtime_token = os.getenv("AI_OS_RUNTIME_TOKEN", "").strip()
    configured = (bool(base_url), bool(runtime_id), bool(runtime_token))
    if not any(configured):
        return
    if not all(configured):
        raise RuntimeError(
            "AI_OS_CONTROL_PLANE_URL, AI_OS_RUNTIME_ID, and AI_OS_RUNTIME_TOKEN must be configured together."
        )
    parsed = urlsplit(base_url)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    if parsed.scheme != "https" and not local_http:
        raise RuntimeError("Control-plane URL must use HTTPS (HTTP is allowed only for localhost).")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("Control-plane URL must not contain credentials, query strings, or fragments.")
    body = json.dumps({
        "runtime_id": runtime_id,
        "status": status,
        "current_job_id": current_job_id,
    }).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/control-plane/runtime-heartbeat",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-AI-Runtime-Token": runtime_token,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError("Control-plane heartbeat was rejected.")


def main() -> None:
    # A separately deployed worker must initialize the same persistent
    # registries and trusted adapters as the API process before polling jobs.
    initialize_database()
    initialize_commerce_storage()
    initialize_control_plane()
    initialize_credential_vault()
    initialize_mcp_broker_storage()
    register_wordpress_draft_adapter()
    register_woocommerce_draft_adapter()
    register_builtin_agent_tools()
    status = get_model_status()
    try:
        interval = int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "3"))
    except ValueError:
        interval = 3
    interval = max(1, min(interval, 60))
    worker_id = f"agent-worker-{uuid4()}"
    logger.info(
        "Worker service started: %s; model_enabled=%s; provider=%s; model=%s",
        worker_id, status["enabled"], status.get("provider"), status.get("model"),
    )
    run_worker_loop(
        worker_id=worker_id,
        poll_seconds=interval,
        stop_requested=lambda: False,
        desired_state=get_worker_desired_state,
        heartbeat=heartbeat_dispatch,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("AI_OS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Agent worker stopped cleanly.")
