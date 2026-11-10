"""Generate bounded source edits and open an isolated draft PR for CI review."""
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from .github_evolution import GitHubEvolutionClient, GitHubPullRequest, validate_evolution_path
from .model_gateway import ModelGateway, ModelRequest


class CodeEvolutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CodeEvolutionResult:
    pull_request: GitHubPullRequest
    provider: str
    model: str
    changed_paths: tuple[str, ...]


def generate_code_evolution_pr(
    problem: str,
    file_paths: tuple[str, ...],
    gateway: ModelGateway,
    github: GitHubEvolutionClient,
) -> CodeEvolutionResult:
    if not problem.strip() or len(problem) > 3000:
        raise ValueError("code evolution problem must contain 1-3000 characters")
    if not 1 <= len(file_paths) <= 3 or len(set(file_paths)) != len(file_paths):
        raise ValueError("select one to three unique source files")
    for path in file_paths:
        validate_evolution_path(path)
    source_files = github.read_files(file_paths)
    if sum(len(value) for value in source_files.values()) > 40000:
        raise CodeEvolutionError("selected source files exceed the 40000-character planning limit")
    prompt = (
        "OPENCOMPANY CONTROLLED CODE EVOLUTION REQUEST\n"
        "You are proposing a code change for the independent OpenCompany codebase. "
        "Return only valid JSON with exactly three keys: title (1-180 chars), "
        "summary (1-3000 chars), files (array of objects with exactly path and content). "
        "Return a complete replacement for every selected file and no other paths. "
        "Preserve existing safety invariants, add or update tests, and do not modify "
        "secrets, credentials, deployment configuration, production data, workflows, "
        "or owner approval boundaries. Do not introduce paid providers or paid fallback. "
        "Do not copy third-party repository code. The output will be committed only to "
        "an isolated feature branch and opened as a DRAFT pull request; it will not merge or deploy.\n"
        f"Problem to solve: {problem}\n"
        f"Selected source files: {json.dumps(source_files, ensure_ascii=False)}"
    )
    result = gateway.complete(
        ModelRequest(prompt=prompt, request_id=str(uuid4()), max_output_tokens=12000),
        request_budget_usd=0.0,
        preferred_provider="unorouter",
    )
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise CodeEvolutionError("code model did not return valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"title", "summary", "files"}:
        raise CodeEvolutionError("code model response must contain only title, summary and files")
    title, summary, changed = payload["title"], payload["summary"], payload["files"]
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 180:
        raise CodeEvolutionError("generated PR title is invalid")
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 3000:
        raise CodeEvolutionError("generated PR summary is invalid")
    if not isinstance(changed, list) or len(changed) != len(file_paths):
        raise CodeEvolutionError("code model must return every selected file exactly once")
    replacements = {}
    for entry in changed:
        if not isinstance(entry, dict) or set(entry) != {"path", "content"}:
            raise CodeEvolutionError("generated file entry has an invalid shape")
        path = validate_evolution_path(entry["path"])
        if path not in source_files or path in replacements:
            raise CodeEvolutionError("generated code attempted to add, omit or duplicate a path")
        replacements[path] = entry["content"]
    if set(replacements) != set(file_paths):
        raise CodeEvolutionError("generated file set differs from the selected file set")
    pr = github.create_pull_request(
        title=title.strip(), summary=summary.strip(), files=replacements
    )
    return CodeEvolutionResult(
        pull_request=pr, provider=result.provider, model=result.model,
        changed_paths=tuple(sorted(replacements)),
    )
