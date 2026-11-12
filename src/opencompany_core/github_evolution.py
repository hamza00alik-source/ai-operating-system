"""GitHub PR-based code evolution; never merges or deploys generated code."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4


class GitHubEvolutionError(RuntimeError):
    pass


_ALLOWED_PREFIXES = ("src/opencompany_core/", "src/opencompany_app/", "tests/", "docs/")
_FORBIDDEN_NAMES = {".env", "secrets.py", "credentials.py", "owner_sessions.py"}
_MAX_FILE_BYTES = 60000


def validate_evolution_path(path: str) -> str:
    if (
        not isinstance(path, str) or not path or path.startswith("/")
        or "\\" in path or ".." in path.split("/")
        or path.split("/")[-1] in _FORBIDDEN_NAMES
        or not path.endswith(".py") and not path.startswith("docs/")
        or not path.startswith(_ALLOWED_PREFIXES)
    ):
        raise ValueError("code evolution path is outside the permitted source, test, or documentation scope")
    return path


@dataclass(frozen=True, slots=True)
class GitHubPullRequest:
    number: int
    url: str
    branch: str
    commit_sha: str
    title: str


class GitHubEvolutionClient:
    """Minimal Git Data API client that writes one atomic commit to a new branch."""

    def __init__(
        self,
        token: str,
        repository: str,
        *,
        base_branch: str = "clean-room-rebuild",
        transport: Callable | None = None,
    ) -> None:
        if not token or len(token) > 512:
            raise ValueError("GitHub token is required")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("repository must be owner/name")
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", base_branch) or ".." in base_branch:
            raise ValueError("invalid base branch")
        self.token = token
        self.repository = repository
        self.base_branch = base_branch
        self._transport = transport or urllib.request.urlopen
        self._api = f"https://api.github.com/repos/{repository}"

    @classmethod
    def from_env(cls) -> "GitHubEvolutionClient | None":
        token = os.environ.get("OPENCOMPANY_GITHUB_TOKEN")
        repository = os.environ.get("OPENCOMPANY_GITHUB_REPOSITORY")
        if not token or not repository:
            return None
        return cls(
            token, repository,
            base_branch=os.environ.get("OPENCOMPANY_GITHUB_BASE_BRANCH", "clean-room-rebuild"),
        )

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self._api + path, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "OpenCompany-Code-Evolution",
            },
        )
        try:
            response = self._transport(request, timeout=30)
            raw = response.read(2_000_000)
            return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            raise GitHubEvolutionError(f"GitHub API rejected code evolution request (HTTP {exc.code})") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise GitHubEvolutionError(f"GitHub API request failed safely ({type(exc).__name__})") from exc



    def verify_access(self) -> dict:
        """Verify token identity and repository visibility using read-only API calls."""
        user = self._request("GET", "/user")
        repository = self._request("GET", "")
        login = user.get("login")
        full_name = repository.get("full_name")
        if not isinstance(login, str) or not login.strip():
            raise GitHubEvolutionError("GitHub did not return an authenticated user identity")
        if not isinstance(full_name, str) or full_name.casefold() != self.repository.casefold():
            raise GitHubEvolutionError("GitHub token cannot read the configured repository")
        permissions = repository.get("permissions")
        push_reported = permissions.get("push") if isinstance(permissions, dict) else None
        if push_reported is False:
            raise GitHubEvolutionError("GitHub token can read the repository but lacks reported push permission")
        return {
            "authenticated": True,
            "username": login,
            "repository_access": True,
            "repository": full_name,
            "base_branch": self.base_branch,
            "push_permission_reported": push_reported,
            "verification_mode": "read_only",
            "auto_merge": False,
            "auto_deploy": False,
        }

    def read_files(self, paths: tuple[str, ...]) -> dict[str, str]:
        if not 1 <= len(paths) <= 3 or len(set(paths)) != len(paths):
            raise ValueError("select one to three unique source files")
        result = {}
        for path in paths:
            validate_evolution_path(path)
            encoded_path = urllib.parse.quote(path, safe="/")
            data = self._request("GET", f"/contents/{encoded_path}?ref={urllib.parse.quote(self.base_branch)}")
            if data.get("type") != "file" or not data.get("content"):
                raise GitHubEvolutionError(f"Selected path is not a readable file: {path}")
            try:
                raw = base64.b64decode(data["content"], validate=False)
                if len(raw) > _MAX_FILE_BYTES:
                    raise ValueError("file too large")
                result[path] = raw.decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubEvolutionError(f"Selected file is not a bounded UTF-8 source file: {path}") from exc
        return result

    def create_pull_request(self, *, title: str, summary: str, files: dict[str, str]) -> GitHubPullRequest:
        if not title.strip() or len(title) > 240 or not summary.strip() or len(summary) > 4000:
            raise ValueError("code change title and summary exceed safe bounds")
        if not 1 <= len(files) <= 3:
            raise ValueError("a code evolution PR must update one to three files")
        for path, content in files.items():
            validate_evolution_path(path)
            if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > _MAX_FILE_BYTES:
                raise ValueError(f"generated file content is empty or exceeds the size limit: {path}")
        base_ref = self._request("GET", f"/git/ref/heads/{urllib.parse.quote(self.base_branch, safe='/')}")
        base_sha = base_ref["object"]["sha"]
        base_commit = self._request("GET", f"/git/commits/{base_sha}")
        branch = f"feat/opencompany-evolution-{uuid4().hex[:12]}"
        branch_created = False
        draft_confirmed = False
        try:
            self._request("POST", "/git/refs", {
                "ref": f"refs/heads/{branch}", "sha": base_sha,
            })
            branch_created = True
            tree_entries = []
            for path, content in sorted(files.items()):
                blob = self._request("POST", "/git/blobs", {
                    "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                    "encoding": "base64",
                })
                tree_entries.append({
                    "path": path, "mode": "100644", "type": "blob", "sha": blob["sha"],
                })
            tree = self._request("POST", "/git/trees", {
                "base_tree": base_commit["tree"]["sha"], "tree": tree_entries,
            })
            commit = self._request("POST", "/git/commits", {
                "message": f"AI proposal: {title}",
                "tree": tree["sha"], "parents": [base_sha],
            })
            self._request("PATCH", f"/git/refs/heads/{urllib.parse.quote(branch, safe='/')}", {
                "sha": commit["sha"], "force": False,
            })
            body = (
                "## OpenCompany AI-generated code proposal\n\n"
                f"{summary}\n\n"
                "### Verification\n"
                "- GitHub Actions must pass before this change is considered.\n"
                "- Human owner review is required before merging into the rebuild branch.\n"
                "- This PR does not merge, deploy, change production, or modify secrets.\n"
            )
            pr = self._request("POST", "/pulls", {
                "title": title, "head": branch, "base": self.base_branch, "body": body,
                "draft": True,
            })
            number = pr.get("number")
            if not isinstance(number, int) or number < 1:
                raise GitHubEvolutionError("GitHub did not return a valid draft pull request number")
            if pr.get("draft") is not True:
                try:
                    self._request("PATCH", f"/pulls/{number}", {"state": "closed"})
                except GitHubEvolutionError:
                    pass
                raise GitHubEvolutionError("GitHub did not confirm draft status; the pull request was closed where possible")
            draft_confirmed = True
            return GitHubPullRequest(
                number=number, url=pr["html_url"], branch=branch,
                commit_sha=commit["sha"], title=title,
            )
        except Exception:
            if branch_created and not draft_confirmed:
                try:
                    self._request("DELETE", f"/git/refs/heads/{urllib.parse.quote(branch, safe='/')}")
                except GitHubEvolutionError:
                    pass
            raise

    def get_pull_request(self, number: int) -> dict:
        if not 1 <= number <= 2_147_483_647:
            raise ValueError("invalid pull request number")
        pr = self._request("GET", f"/pulls/{number}")
        checks = self._request("GET", f"/commits/{pr['head']['sha']}/check-runs")
        return {
            "number": number, "url": pr.get("html_url"), "state": pr.get("state"),
            "draft": bool(pr.get("draft")), "merged": bool(pr.get("merged")),
            "head_sha": pr["head"]["sha"], "base_branch": pr["base"]["ref"],
            "checks": [
                {"name": item.get("name"), "status": item.get("status"), "conclusion": item.get("conclusion")}
                for item in checks.get("check_runs", [])
            ],
        }
