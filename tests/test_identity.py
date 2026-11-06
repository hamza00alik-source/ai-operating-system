import pytest

from ai_os.identity import (
    AgentIdentityError,
    issue_agent_token,
    verify_agent_token,
)


def test_signed_agent_token_round_trip(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    token = issue_agent_token("company-orchestrator")
    principal = verify_agent_token(token, expected_agent_id="company-orchestrator")
    assert principal.agent_id == "company-orchestrator"
    assert principal.expires_at > principal.issued_at
    assert principal.nonce


def test_agent_token_rejects_tampering(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    token = issue_agent_token("company-orchestrator")
    encoded, signature = token.split(".", 1)
    tampered = ("A" if encoded[0] != "A" else "B") + encoded[1:] + "." + signature
    with pytest.raises(AgentIdentityError, match="signature"):
        verify_agent_token(tampered)


def test_agent_token_rejects_wrong_expected_identity(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    token = issue_agent_token("marketing-content-creator")
    with pytest.raises(AgentIdentityError, match="does not match"):
        verify_agent_token(token, expected_agent_id="company-orchestrator")


def test_agent_token_requires_strong_server_secret(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "too-short")
    with pytest.raises(AgentIdentityError, match="at least 32"):
        issue_agent_token("company-orchestrator")


def test_agent_token_ttl_is_bounded(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    with pytest.raises(AgentIdentityError, match="between 1 and 300"):
        issue_agent_token("company-orchestrator", ttl_seconds=301)


def test_expired_agent_token_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_OS_AGENT_SIGNING_KEY", "test-signing-key-" + "x" * 40)
    monkeypatch.setattr("ai_os.identity.time.time", lambda: 1_800_000_000)
    token = issue_agent_token("company-orchestrator", ttl_seconds=1)
    monkeypatch.setattr("ai_os.identity.time.time", lambda: 1_800_000_002)
    with pytest.raises(AgentIdentityError, match="expired"):
        verify_agent_token(token)


def test_malformed_agent_token_is_rejected():
    with pytest.raises(AgentIdentityError, match="Malformed"):
        verify_agent_token("not-a-valid-token")
