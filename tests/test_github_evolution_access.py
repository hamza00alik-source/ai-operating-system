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
