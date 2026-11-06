"""Long-running durable agent worker process. Run: python -m ai_os.worker_service."""
import os
import time
from uuid import uuid4

from ai_os.agent_runtime import schedule_ready_steps
from ai_os.model_adapter import get_model_status
from ai_os.worker import run_once


def main() -> None:
    status = get_model_status()
    if not status["enabled"]:
        raise SystemExit(
            "Agent worker not started: configure an approved model endpoint and "
            "set AI_OS_MODEL_ENABLED=true. No model request was made."
        )
    try:
        interval = int(os.getenv("AI_OS_WORKER_POLL_SECONDS", "3"))
    except ValueError:
        interval = 3
    interval = max(1, min(interval, 60))
    worker_id = f"agent-worker-{uuid4()}"
    print(f"Agent worker started: {worker_id}; provider={status['provider']}; model={status['model']}")
    while True:
        scheduled = schedule_ready_steps()
        result = run_once(worker_id=worker_id)
        if result.get("processed"):
            job = result.get("job") or {}
            print(f"Processed job {job.get('id')} status={job.get('status')}")
            continue
        if scheduled.get("scheduled"):
            continue
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Agent worker stopped cleanly.")
