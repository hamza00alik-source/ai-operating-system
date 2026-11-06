import pytest

from ai_os.identity import (
    AgentIdentityError,
    consume_agent_token,
    issue_agent_token,
    verify_agent_token,
)


def _registered_agent(monkeypatch, *, enabled=True):
    from types import SimpleNamespace
    monkeypatch.setattr(
        "ai_os.registry.get_agent",
        lambda agent_id: SimpleNamespace(id=agent_id, enabled=enabled),
    )


def _token(monkeypatch, **overrides):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    _registered_agent(monkeypatch)
    values = {
        "agent_id": "marketing-content-creator",
        "run_id": "run-123",
        "capabilities": ["step.report"],
    }
    values.update(overrides)
    return issue_agent_token(**values)


def test_signed_agent_token_round_trip(monkeypatch):
    token = _token(monkeypatch)
    principal = verify_agent_token(
        token,
        expected_agent_id="marketing-content-creator",
        expected_run_id="run-123",
        required_capability="step.report",
    )
    assert principal.agent_id == "marketing-content-creator"
    assert principal.run_id == "run-123"
    assert principal.capabilities == ("step.report",)
    assert principal.expires_at > principal.issued_at
    assert principal.nonce


def test_agent_token_rejects_tampering(monkeypatch):
    token = _token(monkeypatch)
    encoded, signature = token.split(".", 1)
    tampered = ("A" if encoded[0] != "A" else "B") + encoded[1:] + "." + signature
    with pytest.raises(AgentIdentityError, match="signature"):
        verify_agent_token(tampered)


def test_agent_token_rejects_wrong_expected_identity(monkeypatch):
    token = _token(monkeypatch)
    with pytest.raises(AgentIdentityError, match="expected principal"):
        verify_agent_token(token, expected_agent_id="company-orchestrator")


def test_agent_token_rejects_wrong_run_and_missing_capability(monkeypatch):
    token = _token(monkeypatch)
    with pytest.raises(AgentIdentityError, match="expected run"):
        verify_agent_token(token, expected_run_id="another-run")
    with pytest.raises(AgentIdentityError, match="required capability"):
        verify_agent_token(token, required_capability="store.publish")


def test_agent_token_requires_strong_server_secret(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "too-short")
    _registered_agent(monkeypatch)
    with pytest.raises(AgentIdentityError, match="at least 32"):
        issue_agent_token(
            "marketing-content-creator",
            run_id="run-123",
            capabilities=["step.report"],
        )


def test_agent_token_ttl_and_capabilities_are_bounded(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    _registered_agent(monkeypatch)
    with pytest.raises(AgentIdentityError, match="between 1 and 300"):
        issue_agent_token("marketing-content-creator", run_id="run-123", capabilities=["x"], ttl_seconds=301)
    with pytest.raises(AgentIdentityError, match="unique"):
        issue_agent_token("marketing-content-creator", run_id="run-123", capabilities=["x", "x"])


def test_disabled_or_unknown_agent_cannot_receive_identity(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    _registered_agent(monkeypatch, enabled=False)
    with pytest.raises(AgentIdentityError, match="enabled server-registered"):
        issue_agent_token("marketing-content-creator", run_id="run-123", capabilities=["research.read"])


def test_expired_agent_token_is_rejected(monkeypatch):
    _registered_agent(monkeypatch)
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    monkeypatch.setattr("ai_os.identity.time.time", lambda: 1_800_000_000)
    token = issue_agent_token("marketing-content-creator", run_id="run-123", capabilities=["step.report"], ttl_seconds=1)
    monkeypatch.setattr("ai_os.identity.time.time", lambda: 1_800_000_002)
    with pytest.raises(AgentIdentityError, match="expired"):
        verify_agent_token(token)


def test_malformed_agent_token_is_rejected():
    with pytest.raises(AgentIdentityError, match="Malformed"):
        verify_agent_token("not-a-valid-token")


def test_agent_token_can_only_be_consumed_once(monkeypatch, tmp_path):
    from ai_os.db import initialize_database
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'identity.db'}")
    initialize_database()
    token = _token(monkeypatch)
    principal = consume_agent_token(token, expected_run_id="run-123", required_capability="step.report")
    assert principal.agent_id == "marketing-content-creator"
    with pytest.raises(AgentIdentityError, match="already consumed"):
        consume_agent_token(token, expected_run_id="run-123")
