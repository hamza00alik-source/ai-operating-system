import json

import pytest

from opencompany_core.github_evolution import GitHubEvolutionClient, GitHubEvolutionError


def test_github_evolution_verify_access_is_read_only():
    calls = []
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def read(self, limit):
            return json.dumps(self.payload).encode("utf-8")
    responses = [
        Response({"login": "owner"}),
        Response({"full_name": "owner/repo", "permissions": {"push": True}}),
    ]
    def transport(request, timeout):
        calls.append((request.method, request.full_url))
        return responses.pop(0)
    client = GitHubEvolutionClient("test-token-value-123456789", "owner/repo", transport=transport)
    result = client.verify_access()
    assert result["authenticated"] is True
    assert result["repository_access"] is True
    assert result["push_permission_reported"] is True
    assert result["verification_mode"] == "read_only"
    assert [method for method, _ in calls] == ["GET", "GET"]
    assert all("/git/refs" not in url and "/pulls" not in url for _, url in calls)


def test_github_evolution_verify_access_rejects_read_only_repository_permission():
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def read(self, limit):
            return json.dumps(self.payload).encode("utf-8")
    responses = [
        Response({"login": "owner"}),
        Response({"full_name": "owner/repo", "permissions": {"push": False}}),
    ]
    client = GitHubEvolutionClient(
        "test-token-value-123456789", "owner/repo",
        transport=lambda request, timeout: responses.pop(0),
    )
    with pytest.raises(GitHubEvolutionError, match="lacks reported push permission"):
        client.verify_access()


def test_code_evolution_creates_only_a_confirmed_draft_pr():
    calls = []
    payloads = [
        {"object": {"sha": "base-sha"}},
        {"tree": {"sha": "base-tree"}},
        {},
        {"sha": "blob-sha"},
        {"sha": "tree-sha"},
        {"sha": "commit-sha"},
        {},
        {"number": 12, "html_url": "https://github.com/owner/repo/pull/12", "draft": True},
    ]
    class Response:
        def __init__(self, data): self.data = data
        def read(self, limit): return json.dumps(self.data).encode()
    def transport(request, timeout):
        calls.append((request.method, request.full_url, request.data))
        return Response(payloads.pop(0))
    client = GitHubEvolutionClient("test-token-value-123456789", "owner/repo", transport=transport)
    result = client.create_pull_request(
        title="Improve safe validation", summary="Add a bounded validation check.",
        files={"src/opencompany_core/example.py": "VALUE = 1\n"},
    )
    assert result.number == 12
    assert [method for method, _, _ in calls] == ["GET", "GET", "POST", "POST", "POST", "POST", "PATCH", "POST"]
    pr_payload = json.loads(calls[-1][2])
    assert pr_payload["draft"] is True
    assert pr_payload["base"] == "clean-room-rebuild"


def test_code_evolution_closes_unconfirmed_non_draft_and_deletes_branch():
    calls = []
    payloads = [
        {"object": {"sha": "base-sha"}},
        {"tree": {"sha": "base-tree"}},
        {},
        {"sha": "blob-sha"},
        {"sha": "tree-sha"},
        {"sha": "commit-sha"},
        {},
        {"number": 13, "html_url": "https://github.com/owner/repo/pull/13", "draft": False},
        {},
        {},
    ]
    class Response:
        def __init__(self, data): self.data = data
        def read(self, limit): return json.dumps(self.data).encode()
    def transport(request, timeout):
        calls.append((request.method, request.full_url, request.data))
        return Response(payloads.pop(0))
    client = GitHubEvolutionClient("test-token-value-123456789", "owner/repo", transport=transport)
    with pytest.raises(GitHubEvolutionError, match="did not confirm draft status"):
        client.create_pull_request(
            title="Improve safe validation", summary="Add a bounded validation check.",
            files={"src/opencompany_core/example.py": "VALUE = 1\n"},
        )
    assert any(method == "PATCH" and url.endswith("/pulls/13") for method, url, _ in calls)
    assert any(method == "DELETE" and "/git/refs/heads/feat/opencompany-evolution-" in url for method, url, _ in calls)
