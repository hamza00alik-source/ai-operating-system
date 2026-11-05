"""Schemas for persistent, zero-API worker jobs."""
from typing import Literal
from pydantic import BaseModel, Field

JobType = Literal["build_work_packet"]
JobStatus = Literal["queued", "running", "completed", "failed"]

class JobCreate(BaseModel):
    job_type: JobType
    payload: dict
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)

class JobOut(BaseModel):
    id: str
    job_type: JobType
    payload: dict
    status: JobStatus
    attempts: int
    max_attempts: int
    result: dict | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None

class WorkerRunOut(BaseModel):
    processed: bool
    job: JobOut | None = None
    notice: str
