"""FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from ai_os.agent_runtime import get_task_memory, list_task_steps
from ai_os.auth import require_api_key
from ai_os.config import get_settings
from ai_os.db import connect, initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision, ApprovalOut, TaskCreate, TaskOut
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.environment != "development" and not settings.api_key:
        raise RuntimeError("AI_OS_API_KEY must be set outside development.")
    initialize_database()
    yield


app = FastAPI(
    title="AI Operating System",
    version="0.1.0",
    description="Human-supervised AI company workflow foundation.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-operating-system"}


@app.post("/tasks", response_model=TaskOut, status_code=201, dependencies=[Depends(require_api_key)])
def post_task(payload: TaskCreate):
    return create_task(payload)


@app.get("/tasks", response_model=list[TaskOut], dependencies=[Depends(require_api_key)])
def get_tasks():
    return list_tasks()


@app.post(
    "/approvals",
    response_model=ApprovalOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def post_approval(payload: ApprovalCreate):
    try:
        return create_approval(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Approval action payload must be valid JSON data.") from exc


@app.get(
    "/approvals",
    response_model=list[ApprovalOut],
    dependencies=[Depends(require_api_key)],
)
def get_approvals():
    return list_approvals()


@app.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalOut,
    dependencies=[Depends(require_api_key)],
)
def post_approval_decision(approval_id: str, payload: ApprovalDecision):
    try:
        result = decide_approval(approval_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return result



@app.get(
    "/tasks/{task_id}/memory",
    dependencies=[Depends(require_api_key)],
)
def get_task_memory_endpoint(task_id: str):
    with connect() as db:
        exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Task not found")
    return get_task_memory(task_id)


@app.get(
    "/tasks/{task_id}/steps",
    dependencies=[Depends(require_api_key)],
)
def get_task_steps_endpoint(task_id: str):
    with connect() as db:
        exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Task not found")
    return list_task_steps(task_id)
