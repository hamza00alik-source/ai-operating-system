import json
import os
import pytest
from cryptography.fernet import Fernet

from ai_os import social_oauth
from ai_os.db import initialize_database


@pytest.fixture
def oauth_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///" + str(tmp_path / "oauth.db"))
    monkeypatch.setenv("AI_OS_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    for provider, prefix in {
        "meta": "META", "tiktok": "TIKTOK", "youtube": "GOOGLE", "etsy": "ETSY",
        "pinterest": "PINTEREST", "reddit": "REDDIT", "x": "X",
    }.items():
        client_id_name = "CLIENT_KEY" if provider == "tiktok" else "CLIENT_ID"
        monkeypatch.setenv("AI_OS_OAUTH_" + prefix + "_" + client_id_name, "client-id-" + provider)
        monkeypatch.setenv("AI_OS_OAUTH_" + prefix + "_CLIENT_SECRET", "client-secret-" + provider)
        monkeypatch.setenv("AI_OS_OAUTH_" + prefix + "_REDIRECT_URI",
            "https://aios.example.com/business-integrations/social/" + provider + "/callback")
    initialize_database()


def test_readiness_reports_missing_provider_app(oauth_env, monkeypatch):
    monkeypatch.delenv("AI_OS_OAUTH_META_CLIENT_SECRET")
    status = {item["provider"]: item for item in social_oauth.readiness()}
    assert status["meta"]["app_configured"] is False
    assert status["tiktok"]["app_configured"] is True


def test_begin_social_oauth_uses_official_authorization_and_scopes(oauth_env):
    url = social_oauth.begin("tiktok", "digital-products")
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert "client_key=client-id-tiktok" in url
    assert "user.info.basic" in url
    assert "digital-products" not in url


def test_oauth_callback_consumes_state_and_saves_verified_account(oauth_env, monkeypatch):
    url = social_oauth.begin("pinterest", "physical-brand")
    from urllib.parse import urlsplit, parse_qs
    state = parse_qs(urlsplit(url).query)["state"][0]
    calls = []
    def fake_request(endpoint, data=None, headers=None):
        calls.append((endpoint, data, headers))
        if endpoint == social_oauth.PROVIDERS["pinterest"]["token"]:
            return {"access_token": "verified-access-token", "expires_in": 3600, "refresh_token": "refresh"}
        return {"username": "brand-account", "id": "42"}
    saved = {}
    monkeypatch.setattr(social_oauth, "_request_json", fake_request)
    monkeypatch.setattr(social_oauth, "save_business_integration",
        lambda business_id, provider, secret, config: saved.update(
            business_id=business_id, provider=provider, secret=json.loads(secret), config=config))
    result = social_oauth.complete("pinterest", state, "one-time-code")
    assert result["connected"] is True
    assert result["business_id"] == "physical-brand"
    assert saved["secret"]["access_token"] == "verified-access-token"
    assert saved["config"]["read_only"] is True
    with pytest.raises(social_oauth.OAuthError, match="invalid, expired, or already used"):
        social_oauth.complete("pinterest", state, "one-time-code")


def test_x_pkce_verifier_is_encrypted_in_state_table(oauth_env):
    from urllib.parse import urlsplit, parse_qs
    from ai_os.db import connect
    url = social_oauth.begin("x", "physical-agency")
    state = parse_qs(urlsplit(url).query)["state"][0]
    with connect() as db:
        row = db.execute("SELECT verifier_encrypted FROM social_oauth_states").fetchone()
    assert row["verifier_encrypted"] is not None
    assert "verifier" not in row["verifier_encrypted"]
    assert social_oauth._fernet().decrypt(row["verifier_encrypted"].encode()).decode()


def test_etsy_pkce_authorization_and_verified_shop_link(oauth_env, monkeypatch):
    from urllib.parse import urlsplit, parse_qs
    url = social_oauth.begin("etsy", "digital-products")
    params = parse_qs(urlsplit(url).query)
    assert url.startswith("https://www.etsy.com/oauth/connect?")
    assert params["scope"] == ["shops_r"]
    assert params["code_challenge_method"] == ["S256"]
    state = params["state"][0]
    def fake_request(endpoint, data=None, headers=None):
        if endpoint == social_oauth.PROVIDERS["etsy"]["token"]:
            assert data["grant_type"] == "authorization_code"
            assert data["client_id"] == "client-id-etsy"
            assert data["code_verifier"]
            return {"access_token": "12345.etsy-access-token", "refresh_token": "etsy-refresh", "expires_in": 3600}
        if endpoint.endswith("/users/me"):
            assert headers["x-api-key"] == "client-id-etsy:client-secret-etsy"
            return {"user_id": 12345, "shop_id": 67890}
        return {"shop_id": 67890, "shop_name": "My Digital Shop"}
    saved = {}
    monkeypatch.setattr(social_oauth, "_request_json", fake_request)
    monkeypatch.setattr(social_oauth, "save_business_integration",
        lambda business_id, provider, secret, config: saved.update(
            business_id=business_id, provider=provider, secret=json.loads(secret), config=config))
    result = social_oauth.complete("etsy", state, "etsy-one-time-code")
    assert result["connected"] is True
    assert result["account"] == "My Digital Shop"
    assert saved["provider"] == "etsy"
    assert saved["config"]["etsy_api_key"] == "client-id-etsy"
    assert saved["secret"]["access_token"] == "12345.etsy-access-token"
