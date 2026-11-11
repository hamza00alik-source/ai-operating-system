import base64
import json
from urllib.parse import urlparse

import pytest

from opencompany_core.code_evolution import CodeEvolutionError, generate_code_evolution_pr
from opencompany_core.github_evolution import GitHubEvolutionClient, validate_evolution_path
from opencompany_core.model_gateway import BillingMode, ModelGateway, ModelResult, ProviderPolicy


class FakeAdapter:
    def __init__(self, text):
        self.text = text
    def generate(self, request, *, model):
        return ModelResult(self.text, "unorouter", model, 0.0)


class FakeGitHub:
    def __init__(self):
        self.source = {"src/opencompany_core/sample.py": "VALUE = 1\n"}
        self.created = None
    def read_files(self, paths):
        return {path: self.source[path] for path in paths}
    def create_pull_request(self, *, title, summary, files):
        self.created = (title, summary, files)
        from opencompany_core.github_evolution import GitHubPullRequest
        return GitHubPullRequest(123, "https://github.com/example/repo/pull/123", "feat/test", "abc123", title)


def gateway(text):
    return ModelGateway.configure(((
        ProviderPolicy("unorouter", "test/free-model:free", BillingMode.FREE_CONFIRMED, 0.0),
        FakeAdapter(text),
    ),))


def test_code_evolution_opens_only_a_draft_pr_with_exact_selected_paths():
    fake = FakeGitHub()
    response = json.dumps({
        "title": "Improve sample implementation",
        "summary": "Add a safe constant and corresponding test coverage.",
        "files": [{"path": "src/opencompany_core/sample.py", "content": "VALUE = 2\n"}],
    })
    result = generate_code_evolution_pr(
        "Improve this sample safely.",
        ("src/opencompany_core/sample.py",),
        gateway(response), fake,
    )
    assert result.pull_request.number == 123
    assert result.pull_request.branch == "feat/test"
    assert fake.created[2] == {"src/opencompany_core/sample.py": "VALUE = 2\n"}
    assert result.changed_paths == ("src/opencompany_core/sample.py",)


def test_code_evolution_rejects_paths_outside_source_and_test_allowlist():
    with pytest.raises(ValueError, match="outside the permitted"):
        validate_evolution_path(".github/workflows/tests.yml")
    with pytest.raises(ValueError, match="outside the permitted"):
        validate_evolution_path("Dockerfile")
    with pytest.raises(ValueError, match="outside the permitted"):
        validate_evolution_path("src/opencompany_core/../secrets.py")


def test_code_evolution_rejects_model_attempt_to_change_unselected_file():
    fake = FakeGitHub()
    response = json.dumps({
        "title": "Unsafe scope", "summary": "Bad",
        "files": [{"path": "Dockerfile", "content": "FROM scratch"}],
    })
    with pytest.raises(ValueError):
        generate_code_evolution_pr(
            "Modify runtime", ("src/opencompany_core/sample.py",), gateway(response), fake
        )
    assert fake.created is None


class FakeResponse:
    def __init__(self, value):
        self.value = value
    def read(self, limit):
        return json.dumps(self.value).encode()


def test_github_client_creates_atomic_feature_branch_commit_and_draft_pr():
    calls = []
    def transport(request, timeout=30):
        path = urlparse(request.full_url).path
        method = request.method
        calls.append((method, path))
        if method == "GET" and path.endswith("/git/ref/heads/clean-room-rebuild"):
            return FakeResponse({"object": {"sha": "base-sha"}})
        if method == "GET" and path.endswith("/git/commits/base-sha"):
            return FakeResponse({"tree": {"sha": "base-tree"}})
        if method == "POST" and path.endswith("/git/refs"):
            return FakeResponse({"ref": "refs/heads/feat/test"})
        if method == "POST" and path.endswith("/git/blobs"):
            return FakeResponse({"sha": "blob-sha"})
        if method == "POST" and path.endswith("/git/trees"):
            return FakeResponse({"sha": "tree-sha"})
        if method == "POST" and path.endswith("/git/commits"):
            return FakeResponse({"sha": "new-commit"})
        if method == "PATCH" and "/git/refs/heads/" in path:
            return FakeResponse({"ref": path})
        if method == "POST" and path.endswith("/pulls"):
            return FakeResponse({"number": 77, "html_url": "https://github.com/a/b/pull/77", "draft": True})
        raise AssertionError((method, path))

    client = GitHubEvolutionClient(
        "test-token", "owner/repo", base_branch="clean-room-rebuild", transport=transport
    )
    pr = client.create_pull_request(
        title="Test code evolution", summary="Safe change",
        files={"src/opencompany_core/sample.py": "VALUE = 3\n"},
    )
    assert pr.number == 77
    assert pr.commit_sha == "new-commit"
    assert pr.branch.startswith("feat/opencompany-evolution-")
    assert ("POST", "/repos/owner/repo/git/trees") in calls
    assert ("POST", "/repos/owner/repo/pulls") in calls
