"""FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from ai_os.auth import require_api_key
from ai_os.cascade import AllProvidersFailed, cascade_chat
from ai_os.cascade_schemas import LLMChatRequest
from ai_os.config import get_settings
from ai_os.db import initialize_database
from ai_os.llm import load_providers, provider_status, test_provider
from ai_os.llm_schemas import LLMTestRequest
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
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-operating-system"}


@app.get("/llm/providers", dependencies=[Depends(require_api_key)])
def get_llm_providers():
    try:
        return provider_status()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/llm/test", dependencies=[Depends(require_api_key)])
async def post_llm_test(payload: LLMTestRequest):
    try:
        return await test_provider(payload.provider, payload.prompt)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        status_code = 503 if str(exc).startswith("Missing API key") else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/llm/chat", dependencies=[Depends(require_api_key)])
async def post_llm_chat(payload: LLMChatRequest):
    try:
        return await cascade_chat(
            payload.prompt,
            system=payload.system,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
        )
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AllProvidersFailed as exc:
        # Provider names and sanitized failure categories only; no keys or raw bodies.
        raise HTTPException(status_code=502, detail={
            "message": str(exc),
            "failures": exc.failures,
        }) from exc


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
