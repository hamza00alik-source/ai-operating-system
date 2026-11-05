"""Bounded local worker. Only explicitly registered, no-network handlers run here."""
from uuid import uuid4

from ai_os.queue import claim_next_job, fail_job, finish_job
from ai_os.work_packets import build_work_packet

def _build_work_packet(payload: dict) -> dict:
    packet = build_work_packet(
        agent_id=payload["agent_id"],
        task=payload["task"],
        context=payload.get("context", ""),
    )
    return packet.model_dump() if hasattr(packet, "model_dump") else dict(packet)

HANDLERS = {
    "build_work_packet": _build_work_packet,
}

def run_once(worker_id: str | None = None) -> dict:
    worker_id = worker_id or f"local-{uuid4()}"
    job = claim_next_job(worker_id)
    if job is None:
        return {"processed": False, "job": None,
                "notice": "No queued job is available. No model or external service was called."}
    try:
        handler = HANDLERS.get(job["job_type"])
        if handler is None:
            raise ValueError("No handler is registered for this job type")
        result = handler(job["payload"])
        completed = finish_job(job["id"], worker_id, result)
        return {"processed": True, "job": completed,
                "notice": "Job completed locally. No model API or external action was used."}
    except (KeyError, TypeError, ValueError, LookupError) as exc:
        failed = fail_job(job["id"], worker_id, str(exc))
        return {"processed": True, "job": failed,
                "notice": "Job handler failed safely; retry policy is recorded in the queue."}
    except Exception as exc:
        failed = fail_job(job["id"], worker_id, f"Unexpected handler error: {type(exc).__name__}")
        return {"processed": True, "job": failed,
                "notice": "Unexpected error recorded; no external action was attempted."}
