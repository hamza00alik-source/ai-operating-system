"""FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from ai_os.owner_dashboard import owner_dashboard

from ai_os.auth import require_api_key
from ai_os.config import get_settings
from ai_os.db import initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision, ApprovalOut, TaskCreate, TaskOut
from ai_os.service import create_approval, create_task, decide_approval, list_approvals, list_tasks
from ai_os.discovery import create_scan, list_scans, list_candidates
from ai_os.schemas import DiscoveryScanCreate
from ai_os.llm_gateway import list_providers, generate, test_provider
from pydantic import BaseModel, Field


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


@app.get("/owner", include_in_schema=False)
def get_owner_dashboard():
    return owner_dashboard()


class ModelRunRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=8000)


@app.get("/llm/providers", dependencies=[Depends(require_api_key)])
def get_llm_providers():
    return list_providers()


@app.post("/llm/test", dependencies=[Depends(require_api_key)])
def post_llm_test(payload: ModelRunRequest):
    try:
        return test_provider(payload.provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/llm/run", dependencies=[Depends(require_api_key)])
def post_llm_run(payload: ModelRunRequest):
    try:
        return generate(payload.provider, payload.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


@app.post("/discovery/scans", status_code=202, dependencies=[Depends(require_api_key)])
def post_discovery_scan(payload: DiscoveryScanCreate):
    try:
        return create_scan(payload.categories)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/discovery/scans", dependencies=[Depends(require_api_key)])
def get_discovery_scans():
    return list_scans()


@app.get("/discovery/candidates", dependencies=[Depends(require_api_key)])
def get_discovery_candidates():
    return list_candidates()
