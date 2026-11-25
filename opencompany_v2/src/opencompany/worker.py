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
            if not self.queue.complete(job["id"], self.worker_id, result, job["attempts"]):
                return {"job_id": job["id"], "status": "lease_lost"}
            return {"job_id": job["id"], "status": "completed", "result": result}
        except Exception as exc:
            self.queue.fail(job["id"], self.worker_id, f"{type(exc).__name__}: {exc}", job["attempts"])
            return {"job_id": job["id"], "status": "failed", "error": str(exc)}


class AgentWorker:
    """Run one job for one agent, enforcing persisted skill assignment.

    Only handlers registered in SkillRegistry are executable. Job payloads are
    untrusted; identity, skill version, and capabilities are rechecked before
    the handler is invoked.
    """
    def __init__(self, agent_id: str, store, queue, registry,
                 actions: dict[str, str], lease_seconds: int = 60,
                 approval_resolver=None, task_service=None):
        if not agent_id or lease_seconds < 1:
            raise ValueError("agent_id and positive lease_seconds are required")
        self.agent_id, self.store, self.queue = agent_id, store, queue
        self.registry, self.actions = registry, dict(actions)
        self.lease_seconds = lease_seconds
        self.approval_resolver = approval_resolver
        self.task_service = task_service

    def run_once(self):
        import json
        from opencompany.agent import AgentResult
        from opencompany.domain import CompanyEvent
        profile = self.store.get_agent_profile(self.agent_id)
        if profile is None:
            raise KeyError("agent profile not found")
        # Repair the durable-result/queue-ack crash window before claiming
        # new work. This is idempotent and only advances RUNNING tasks whose
        # completed queue job matches the task's persisted result identity.
        if self.task_service is not None:
            self.task_service.reconcile_completed_jobs(self.queue)
        worker_id = f"agent-worker:{self.agent_id}"
        job = self.queue.claim(worker_id, self.lease_seconds, agent_id=self.agent_id)
        if job is None:
            return None
        job_id, task_id = job["id"], job["task_id"]
        try:
            payload = json.loads(job["payload"])
            if payload.get("agent_id") != self.agent_id or payload.get("task_id") != task_id:
                raise PermissionError("Job identity does not match leased task")
            skill_key, skill_version = payload.get("skill_key"), payload.get("skill_version")
            assignment = next((x for x in self.store.list_skill_assignments(self.agent_id)
                               if x["skill_key"] == skill_key and x["skill_version"] == skill_version), None)
            if assignment is None:
                raise PermissionError("Assigned skill is no longer active")
            contract = next((x for x in self.registry.list()
                             if x["key"] == skill_key and x["version"] == skill_version), None)
            if contract is None:
                raise PermissionError("Registered skill version is unavailable")
            if not set(contract["required_capabilities"]).issubset(profile.capabilities):
                raise PermissionError("Agent no longer meets skill capabilities")
            action = self.actions.get(skill_key)
            if action is None:
                raise PermissionError("No worker action is configured for this skill")
            handler = self.registry.worker_handler(skill_key, action,
                        approval_resolver=self.approval_resolver)
            if self.task_service is not None:
                from opencompany.domain import TaskStatus
                task = next((x for x in self.store.list_tasks() if x["id"] == task_id), None)
                if task is None:
                    raise KeyError("task not found")
                if task["status"] == TaskStatus.READY.value:
                    self.task_service.move(task_id, TaskStatus.RUNNING, actor=self.agent_id)
                elif task["status"] != TaskStatus.RUNNING.value:
                    raise ValueError("task must be READY or RUNNING to execute")
                elif task.get("execution_result_job_id") == str(job_id):
                    # A previous attempt persisted its result but crashed before
                    # queue acknowledgement. Reuse that durable result; never rerun
                    # the handler for this task/job pair.
                    saved = task.get("execution_result")
                    if not isinstance(saved, dict):
                        raise ValueError("persisted execution result is invalid")
                    if not self.queue.complete(job_id, worker_id, saved, job["attempts"]):
                        return {"job_id": job_id, "status": "lease_lost"}
                    target = {
                        "completed": TaskStatus.COMPLETED,
                        "failed": TaskStatus.FAILED,
                        "blocked": TaskStatus.BLOCKED,
                        "approval_required": TaskStatus.WAITING_APPROVAL,
                    }.get(saved.get("status"))
                    if target is None:
                        raise ValueError("persisted execution result status is invalid")
                    self.task_service.move(task_id, target, actor=self.agent_id)
                    return saved
            self.store.append_event(CompanyEvent("agent_execution_started", self.agent_id,
                "task", task_id, {"job_id": job_id, "skill_key": skill_key, "skill_version": skill_version}))
            raw = handler(payload)
            output = raw["output"]
            result = AgentResult(
                status=output.get("status", "completed"),
                summary=output.get("summary", ""),
                artifacts=tuple(output.get("artifacts", ())),
                steps_used=output.get("steps_used", 0),
            ).validate(profile.max_steps)
            report = {"status": result.status, "summary": result.summary,
                "artifacts": list(result.artifacts), "steps_used": result.steps_used,
                "agent_id": self.agent_id, "skill_key": skill_key, "skill_version": skill_version}
            if self.task_service is not None:
                for message in output.get("progress", []):
                    self.task_service.record_progress(task_id, self.agent_id, job_id, message)
                self.task_service.record_result(task_id, self.agent_id, job_id, report)
            if not self.queue.complete(job_id, worker_id, report, job["attempts"]):
                raise RuntimeError("Execution lease was lost before result acknowledgement")
            if self.task_service is not None:
                from opencompany.domain import TaskStatus
                target = {
                    "completed": TaskStatus.COMPLETED,
                    "failed": TaskStatus.FAILED,
                    "blocked": TaskStatus.BLOCKED,
                    "approval_required": TaskStatus.WAITING_APPROVAL,
                }[result.status]
                self.task_service.move(task_id, target, actor=self.agent_id)
            self.store.append_event(CompanyEvent("agent_execution_result", self.agent_id,
                "task", task_id, {"job_id": job_id, **report}))
            return report
        except Exception as exc:
            self.queue.fail(job_id, worker_id, f"{type(exc).__name__}: {exc}", job["attempts"])
            self.store.append_event(CompanyEvent("agent_execution_failed", self.agent_id,
                "task", task_id, {"job_id": job_id, "error": f"{type(exc).__name__}: {exc}"[:2000]}))
            raise
