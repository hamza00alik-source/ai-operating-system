"""Bounded worker loop primitives; no network or paid provider dependency."""
from __future__ import annotations
from collections.abc import Callable
from typing import Any


class Worker:
    def __init__(self, queue, worker_id: str, handlers: dict[str, Callable[[dict], dict]],
                 lease_seconds: int = 60):
        if not worker_id:
            raise ValueError("worker_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self.queue = queue
        self.worker_id = worker_id
        self.handlers = handlers
        self.lease_seconds = lease_seconds

    def run_once(self) -> dict[str, Any] | None:
        job = self.queue.claim(self.worker_id, self.lease_seconds)
        if job is None:
            return None
        payload = job["payload"]
        import json
        try:
            data = json.loads(payload)
            handler_name = data.get("handler")
            handler = self.handlers.get(handler_name)
            if handler is None:
                raise ValueError(f"No registered handler: {handler_name}")
            result = handler(data.get("input", {}))
            if not isinstance(result, dict):
                raise TypeError("Worker handlers must return a dictionary")
            if not self.queue.complete(job["id"], self.worker_id, result):
                return {"job_id": job["id"], "status": "lease_lost"}
            return {"job_id": job["id"], "status": "completed", "result": result}
        except Exception as exc:
            self.queue.fail(job["id"], self.worker_id, f"{type(exc).__name__}: {exc}")
            return {"job_id": job["id"], "status": "failed", "error": str(exc)}
