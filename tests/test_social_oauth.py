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
        secret_name = "SHARED_SECRET" if provider == "etsy" else "CLIENT_SECRET"
        monkeypatch.setenv("AI_OS_OAUTH_" + prefix + "_" + secret_name, "client-secret-" + provider)
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


def test_etsy_saved_connection_retest_is_read_only(oauth_env, monkeypatch):
    import time
    credential = json.dumps({"access_token": "12345.token", "expires_at": int(time.time()) + 3600})
    calls = []
    def fake_request(endpoint, data=None, headers=None):
        calls.append((endpoint, data, headers))
        if endpoint.endswith("/users/me"):
            return {"user_id": 12345, "shop_id": 67890}
        return {"shop_id": 67890, "shop_name": "My Digital Shop"}
    monkeypatch.setattr(social_oauth, "_request_json", fake_request)
    result = social_oauth.verify_etsy_credential(credential, {
        "etsy_api_key": "etsy-key", "etsy_shared_secret": "etsy-shared-secret"})
    assert result["connected"] is True
    assert result["account"] == "My Digital Shop"
    assert all(call[1] is None for call in calls)
    assert all(call[2]["Authorization"] == "Bearer 12345.token" for call in calls)
    assert all(call[2]["x-api-key"] == "etsy-key:etsy-shared-secret" for call in calls)


def test_etsy_retest_refreshes_expired_access_token_and_persists_rotation(oauth_env, monkeypatch):
    import time
    credential = json.dumps({"access_token": "12345.old-token", "refresh_token": "12345.refresh",
                             "expires_at": int(time.time()) - 1, "scope": "shops_r"})
    calls, saved = [], {}
    def fake_request(endpoint, data=None, headers=None):
        calls.append((endpoint, data, headers))
        if endpoint == social_oauth.PROVIDERS["etsy"]["token"]:
            assert data == {"grant_type": "refresh_token", "client_id": "etsy-key",
                            "refresh_token": "12345.refresh"}
            return {"access_token": "12345.new-token", "refresh_token": "12345.rotated",
                    "expires_in": 3600, "token_type": "Bearer", "scope": "shops_r"}
        if endpoint.endswith("/users/me"):
            assert headers["Authorization"] == "Bearer 12345.new-token"
            return {"user_id": 12345, "shop_id": 67890}
        return {"shop_id": 67890, "shop_name": "My Digital Shop"}
    monkeypatch.setattr(social_oauth, "_request_json", fake_request)
    monkeypatch.setattr(social_oauth, "save_business_integration",
        lambda business_id, provider, secret, config: saved.update(
            business_id=business_id, provider=provider, secret=json.loads(secret), config=config))
    result = social_oauth.verify_etsy_credential(credential, {
        "etsy_api_key": "etsy-key", "etsy_shared_secret": "etsy-shared-secret"}, "digital-products")
    assert result["connected"] is True
    assert result["token_refreshed"] is True
    assert saved["business_id"] == "digital-products"
    assert saved["secret"]["access_token"] == "12345.new-token"
    assert saved["secret"]["refresh_token"] == "12345.rotated"
    assert saved["config"]["etsy_api_key"] == "etsy-key"


def test_etsy_retest_expired_without_refresh_token_requires_reauthorization(oauth_env):
    import time
    credential = json.dumps({"access_token": "12345.token", "expires_at": int(time.time()) - 1})
    with pytest.raises(social_oauth.OAuthError, match="no refresh token"):
        social_oauth.verify_etsy_credential(credential, {
            "etsy_api_key": "etsy-key", "etsy_shared_secret": "etsy-shared-secret"})


@pytest.mark.parametrize("provider,identity,expected", [
    ("meta", {"id": "m-1", "name": "Meta Page Owner"}, "Meta Page Owner"),
    ("tiktok", {"data": {"user": {"open_id": "tt-1", "display_name": "TikTok Owner"}}}, "TikTok Owner"),
    ("youtube", {"items": [{"id": "yt-1", "snippet": {"title": "YouTube Channel"}}]}, "YouTube Channel"),
    ("pinterest", {"id": "p-1", "username": "pin-owner"}, "pin-owner"),
    ("reddit", {"id": "r-1", "name": "reddit-owner"}, "reddit-owner"),
    ("x", {"data": {"id": "x-1", "name": "X Owner", "username": "x-owner"}}, "X Owner"),
])
def test_saved_social_account_verification_is_read_only(oauth_env, monkeypatch, provider, identity, expected):
    credential = json.dumps({"access_token": "valid-access-token", "expires_at": 4102444800})
    calls = []
    def fake_request(endpoint, data=None, headers=None):
        calls.append((endpoint, data, headers))
        return identity
    monkeypatch.setattr(social_oauth, "_request_json", fake_request)
    result = social_oauth.verify_social_credential(provider, credential, {"read_only": True}, "physical-agency")
    assert result["connected"] is True
    assert result["account"] == expected
    assert result["token_refreshed"] is False
    assert len(calls) == 1
    assert calls[0][1] is None
    assert calls[0][2]["Authorization"] == "Bearer valid-access-token"


def test_tiktok_expired_token_refresh_rotates_and_persists(oauth_env, monkeypatch):
    import time
    credential = json.dumps({"access_token": "old-access", "refresh_token": "old-refresh",
                             "expires_at": int(time.time()) - 1})
    calls, saved = [], {}
    def fake_request(endpoint, data=None, headers=None):
        calls.append((endpoint, data, headers))
        if endpoint == social_oauth.PROVIDERS["tiktok"]["token"]:
            assert data["grant_type"] == "refresh_token"
            assert data["client_key"] == "client-id-tiktok"
            assert data["refresh_token"] == "old-refresh"
            return {"access_token": "new-access", "refresh_token": "rotated-refresh", "expires_in": 7200, "refresh_expires_in": 15552000}
        return {"data": {"user": {"open_id": "tt-1", "display_name": "TikTok Owner"}}}
    monkeypatch.setattr(social_oauth, "_request_json", fake_request)
    monkeypatch.setattr(social_oauth, "save_business_integration",
        lambda business_id, provider, secret, config: saved.update(
            business_id=business_id, provider=provider, secret=json.loads(secret), config=config))
    result = social_oauth.verify_social_credential("tiktok", credential, {"read_only": True}, "digital-products")
    assert result["token_refreshed"] is True
    assert saved["business_id"] == "digital-products"
    assert saved["secret"]["access_token"] == "new-access"
    assert saved["secret"]["refresh_token"] == "rotated-refresh"
    assert saved["secret"]["refresh_expires_at"] > int(time.time())
    assert calls[-1][2]["Authorization"] == "Bearer new-access"


def test_expired_nonrefreshable_social_token_requires_reconnect(oauth_env):
    import time
    credential = json.dumps({"access_token": "expired", "expires_at": int(time.time()) - 1})
    with pytest.raises(social_oauth.OAuthError, match="expired; reconnect"):
        social_oauth.verify_social_credential("meta", credential, {}, "physical-brand")

