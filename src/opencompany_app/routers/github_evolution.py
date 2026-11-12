"""Owner-controlled GitHub integration and draft-only code-evolution routes.

GitHub settings and proposal workflows remain owner-authenticated. Code changes
are submitted only as draft pull requests; this router never merges or deploys.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_core.secret_vault import SecretVaultError
from opencompany_core.github_evolution import GitHubEvolutionError
from opencompany_core.code_evolution import CodeEvolutionError, generate_code_evolution_pr
from opencompany_core.model_gateway import CostPolicyViolation, NoEligibleProvider, ProviderUnavailable
from opencompany_app.api_schemas import GitHubEvolutionSettingsInput, CodeEvolutionInput
from opencompany_app.api_dependencies import get_runtime, get_store, require_owner_key
from opencompany_app.runtime import OpenCompanyRuntime


settings_router = APIRouter()
evolution_router = APIRouter()


@settings_router.get("/settings/integrations/github-evolution", dependencies=[Depends(require_owner_key)])
def get_github_evolution_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    return {
        "configured": runtime.github_evolution is not None,
        "repository": runtime.github_evolution.repository if runtime.github_evolution else os.environ.get("OPENCOMPANY_GITHUB_REPOSITORY"),
        "base_branch": runtime.github_evolution.base_branch if runtime.github_evolution else os.environ.get("OPENCOMPANY_GITHUB_BASE_BRANCH", "clean-room-rebuild"),
        "token_present": runtime.secret_vault.status("github_evolution")["configured"],
        "configuration_error": runtime.secret_vault_errors.get("github_evolution"),
        "access_verified": runtime.github_evolution_tested_at is not None,
        "verified_at": runtime.github_evolution_tested_at,
        "token": None,
        "auto_merge": False,
        "auto_deploy": False,
        "allowed_output": "draft_pull_requests_only",
    }


@settings_router.put("/settings/integrations/github-evolution", dependencies=[Depends(require_owner_key)])
def save_github_evolution_settings(
    payload: GitHubEvolutionSettingsInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if payload.confirm_draft_pr_only is not True:
        raise HTTPException(status_code=422, detail="Owner must confirm GitHub access is for draft PR creation only.")
    if not os.environ.get("OPENCOMPANY_GITHUB_REPOSITORY", "").strip():
        raise HTTPException(status_code=503, detail="The GitHub repository must be configured by the service owner before saving a token.")
    try:
        runtime.secret_vault.put("github_evolution", {"token": payload.token})
        runtime.configure_github_evolution(payload.token)
    except (SecretVaultError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="GitHub credentials could not be saved safely.") from exc
    return {
        "configured": True,
        "repository": runtime.github_evolution.repository,
        "base_branch": runtime.github_evolution.base_branch,
        "token_saved": True,
        "token_echoed": False,
        "auto_merge": False,
        "auto_deploy": False,
    }


@settings_router.post("/settings/integrations/github-evolution/test", dependencies=[Depends(require_owner_key)])
def test_github_evolution_access(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    if runtime.github_evolution is None:
        raise HTTPException(status_code=503, detail="GitHub code evolution is not configured.")
    try:
        result = runtime.github_evolution.verify_access()
    except GitHubEvolutionError as exc:
        runtime.github_evolution_tested_at = None
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    runtime.github_evolution_tested_at = datetime.now(timezone.utc).isoformat()
    return {**result, "verified_at": runtime.github_evolution_tested_at}


@settings_router.delete("/settings/integrations/github-evolution", dependencies=[Depends(require_owner_key)])
def remove_github_evolution_settings(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    try:
        removed = runtime.secret_vault.delete("github_evolution")
        runtime.configure_github_evolution(None)
    except SecretVaultError as exc:
        raise HTTPException(status_code=503, detail="GitHub credentials could not be removed safely.") from exc
    return {"removed": removed, "configured": False, "token_echoed": False, "auto_merge": False, "auto_deploy": False}


@evolution_router.get("/code-evolution/config-status", dependencies=[Depends(require_owner_key)])
def code_evolution_config_status(runtime: OpenCompanyRuntime = Depends(get_runtime)) -> dict:
    provider_verified = runtime.unorouter_tested_at is not None
    github_verified = runtime.github_evolution_tested_at is not None
    return {
        "configured": runtime.github_evolution is not None,
        "enabled": runtime.github_evolution is not None and github_verified and provider_verified,
        "access_verified": github_verified,
        "provider_verified": provider_verified,
        "verified_at": runtime.github_evolution_tested_at,
        "repository": runtime.github_evolution.repository if runtime.github_evolution else None,
        "base_branch": runtime.github_evolution.base_branch if runtime.github_evolution else None,
        "auto_merge": False,
        "auto_deploy": False,
    }


@evolution_router.post("/code-evolution/proposals", dependencies=[Depends(require_owner_key)])
def create_code_evolution_proposal(
    payload: CodeEvolutionInput,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
    store: SQLiteStore = Depends(get_store),
) -> dict:
    """Generate source edits and open a draft PR on an isolated feature branch."""
    if runtime.github_evolution is None:
        raise HTTPException(
            status_code=503,
            detail="Code evolution is not connected. Configure the repository on the service and save a GitHub token in the owner dashboard.",
        )
    if runtime.unorouter_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the owner-triggered zero-cost UnoRouter test before creating code-evolution proposals.")
    if runtime.github_evolution_tested_at is None:
        raise HTTPException(status_code=409, detail="Run the read-only GitHub repository access test before creating code-evolution proposals.")
    try:
        result = generate_code_evolution_pr(
            payload.problem, tuple(payload.file_paths),
            runtime.gateway, runtime.github_evolution,
        )
    except NoEligibleProvider as exc:
        raise HTTPException(status_code=503, detail="No owner-configured free model provider is available for code evolution.") from exc
    except (ProviderUnavailable, CostPolicyViolation) as exc:
        raise HTTPException(status_code=502, detail=f"Code model request failed safely: {type(exc).__name__}") from exc
    except (CodeEvolutionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubEvolutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    store.append_audit_record(AuditRecord(
        id=uuid4(), occurred_at=now, actor_type="owner", actor_id="owner",
        action="code_evolution.draft_pull_request_created",
        subject_type="github_pull_request", subject_id=str(result.pull_request.number),
        outcome="draft_pr_created", correlation_id=str(uuid4()),
        details={
            "url": result.pull_request.url, "branch": result.pull_request.branch,
            "commit_sha": result.pull_request.commit_sha,
            "changed_paths": list(result.changed_paths),
            "provider": result.provider, "model": result.model,
        },
    ))
    return {
        "pull_request_number": result.pull_request.number,
        "url": result.pull_request.url,
        "branch": result.pull_request.branch,
        "commit_sha": result.pull_request.commit_sha,
        "changed_paths": list(result.changed_paths),
        "provider": result.provider,
        "model": result.model,
        "draft": True,
        "merged": False,
        "deployed": False,
        "owner_merge_review_required": True,
    }


@evolution_router.get("/code-evolution/pull-requests/{number}", dependencies=[Depends(require_owner_key)])
def get_code_evolution_status(
    number: int,
    runtime: OpenCompanyRuntime = Depends(get_runtime),
) -> dict:
    if runtime.github_evolution is None:
        raise HTTPException(status_code=503, detail="GitHub code evolution is not configured.")
    try:
        status = runtime.github_evolution.get_pull_request(number)
    except (ValueError, GitHubEvolutionError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return status

