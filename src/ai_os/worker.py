"""Durable worker for local jobs and model-backed specialist steps."""
from uuid import uuid4
from threading import Event, Thread

from ai_os.agent_runtime import execute_company_step
from ai_os.department_coordination import review_department_plan
from ai_os.execution import mark_company_step_blocked
from ai_os.model_adapter import get_model_status
from ai_os.queue import claim_next_job, fail_job, finish_job, renew_job_lease
from ai_os.work_packets import build_work_packet


def _review_department_plan(payload: dict) -> dict:
    run_id, department_id = payload.get("run_id"), payload.get("department_id")
    if not isinstance(run_id, str) or not isinstance(department_id, str):
        raise ValueError("review_department_plan requires run_id and department_id")
    return review_department_plan(run_id, department_id)


def _build_work_packet(payload: dict) -> dict:
    packet = build_work_packet(agent_id=payload["agent_id"], task=payload["task"],
                               context=payload.get("context", ""))
    return packet.model_dump() if hasattr(packet, "model_dump") else dict(packet)


HANDLERS = {
    "build_work_packet": _build_work_packet,
    "execute_company_step": execute_company_step,
    "review_department_plan": _review_department_plan,
}


def _fail_claimed_job(job: dict, worker_id: str, error: str) -> dict | None:
    failed = fail_job(job["id"], worker_id, error)
    if (
        failed
        and failed["status"] == "failed"
        and job["job_type"] == "execute_company_step"
    ):
        payload = job["payload"]
        if isinstance(payload.get("run_id"), str) and isinstance(payload.get("step_key"), str):
            mark_company_step_blocked(
                payload["run_id"], payload["step_key"],
                "Specialist execution stopped after retries: " + error[:800],
            )
    return failed


def run_once(worker_id: str | None = None) -> dict:
    worker_id = worker_id or f"local-{uuid4()}"
    model_enabled = get_model_status()["enabled"]
    allowed_job_types = set(HANDLERS)
    if not model_enabled:
        # Keep local packet-building and manager-review tasks available, but leave
        # specialist inference jobs queued until an approved model is enabled.
        allowed_job_types.discard("execute_company_step")
    job = claim_next_job(worker_id, allowed_job_types=allowed_job_types)
    if job is None:
        return {
            "processed": False,
            "job": None,
            "notice": (
                "No eligible queued job is available. Model-backed specialist jobs "
                "remain queued while model execution is disabled."
                if not model_enabled
                else "No queued job is available."
            ),
        }

    stop_heartbeat = Event()

    def maintain_lease():
        while not stop_heartbeat.wait(30):
            if not renew_job_lease(job["id"], worker_id, lease_seconds=120):
                return

    heartbeat_thread = Thread(target=maintain_lease, name=f"lease-{job['id'][:8]}", daemon=True)
    heartbeat_thread.start()
    try:
        handler = HANDLERS.get(job["job_type"])
        if handler is None:
            raise ValueError("No handler is registered for this job type")
        result = handler(job["payload"])
        completed = finish_job(job["id"], worker_id, result)
        notices = {
            "execute_company_step": "Specialist model task completed; no external action was attempted.",
            "review_department_plan": "Department manager review completed and recorded for the CEO; no external action was attempted.",
            "build_work_packet": "Work packet completed locally; no model or external service was called.",
        }
        notice = notices.get(job["job_type"], "Job completed safely.")
        return {"processed": True, "job": completed, "notice": notice}
    except (KeyError, TypeError, ValueError, LookupError) as exc:
        failed = _fail_claimed_job(job, worker_id, str(exc))
        return {"processed": True, "job": failed,
                "notice": "Job handler failed safely; retry policy is recorded in the queue."}
    except Exception as exc:
        failed = _fail_claimed_job(
            job, worker_id, f"Unexpected handler error: {type(exc).__name__}"
        )
        return {"processed": True, "job": failed,
                "notice": "Unexpected error recorded; no external action was attempted."}
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
