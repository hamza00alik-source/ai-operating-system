"""Server-side OAuth 2.0 account linking for social channels.

Only read-oriented scopes are requested. The module never publishes, messages,
creates listings, or performs financial actions. Provider app credentials and
exact callback URLs are configured as server environment variables.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ai_os.db import connect
from ai_os.credentials import save_business_integration, _fernet, CredentialVaultUnavailable

class OAuthError(RuntimeError):
    pass

class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            raise OAuthError("Cross-origin OAuth endpoint redirect blocked.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

# Meta is one OAuth app for Facebook Pages and linked Instagram professional
# accounts. The owner chooses the business environment in the dashboard.
PROVIDERS = {
    "meta": {
        "label": "Meta · Facebook Pages and linked Instagram professional accounts",
        "client_id_env": "AI_OS_OAUTH_META_CLIENT_ID",
        "client_secret_env": "AI_OS_OAUTH_META_CLIENT_SECRET",
        "redirect_env": "AI_OS_OAUTH_META_REDIRECT_URI",
        "authorize": "https://www.facebook.com/v24.0/dialog/oauth",
        "token": "https://graph.facebook.com/v24.0/oauth/access_token",
        "scopes": ["pages_show_list", "pages_read_engagement", "instagram_basic"],
        "token_mode": "query",
        "identity": "https://graph.facebook.com/v24.0/me?fields=id,name",
    },
    "tiktok": {
        "label": "TikTok",
        "client_id_env": "AI_OS_OAUTH_TIKTOK_CLIENT_KEY",
        "client_secret_env": "AI_OS_OAUTH_TIKTOK_CLIENT_SECRET",
        "redirect_env": "AI_OS_OAUTH_TIKTOK_REDIRECT_URI",
        "authorize": "https://www.tiktok.com/v2/auth/authorize/",
        "token": "https://open.tiktokapis.com/v2/oauth/token/",
        "scopes": ["user.info.basic", "video.list"],
        "token_mode": "tiktok",
        "identity": "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name",
    },
    "youtube": {
        "label": "YouTube (Google)",
        "client_id_env": "AI_OS_OAUTH_GOOGLE_CLIENT_ID",
        "client_secret_env": "AI_OS_OAUTH_GOOGLE_CLIENT_SECRET",
        "redirect_env": "AI_OS_OAUTH_GOOGLE_REDIRECT_URI",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        "token_mode": "form",
        "identity": "https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true",
        "extra_authorize": {"access_type": "offline", "prompt": "consent"},
    },
    "pinterest": {
        "label": "Pinterest",
        "client_id_env": "AI_OS_OAUTH_PINTEREST_CLIENT_ID",
        "client_secret_env": "AI_OS_OAUTH_PINTEREST_CLIENT_SECRET",
        "redirect_env": "AI_OS_OAUTH_PINTEREST_REDIRECT_URI",
        "authorize": "https://www.pinterest.com/oauth/",
        "token": "https://api.pinterest.com/v5/oauth/token",
        "scopes": ["boards:read", "pins:read", "user_accounts:read"],
        "token_mode": "basic_form",
        "identity": "https://api.pinterest.com/v5/user_account",
    },
    "reddit": {
        "label": "Reddit",
        "client_id_env": "AI_OS_OAUTH_REDDIT_CLIENT_ID",
        "client_secret_env": "AI_OS_OAUTH_REDDIT_CLIENT_SECRET",
        "redirect_env": "AI_OS_OAUTH_REDDIT_REDIRECT_URI",
        "authorize": "https://www.reddit.com/api/v1/authorize",
        "token": "https://www.reddit.com/api/v1/access_token",
        "scopes": ["identity", "read"],
        "token_mode": "basic_form",
        "identity": "https://oauth.reddit.com/api/v1/me",
    },
    "etsy": {
        "label": "Etsy shop",
        "client_id_env": "AI_OS_OAUTH_ETSY_CLIENT_ID",
        "client_secret_env": "AI_OS_OAUTH_ETSY_SHARED_SECRET",
        "redirect_env": "AI_OS_OAUTH_ETSY_REDIRECT_URI",
        "authorize": "https://www.etsy.com/oauth/connect",
        "token": "https://api.etsy.com/v3/public/oauth/token",
        "scopes": ["shops_r"],
        "token_mode": "etsy_pkce",
        "identity": "https://api.etsy.com/v3/application/users/me",
    },
    "x": {
        "label": "X",
        "client_id_env": "AI_OS_OAUTH_X_CLIENT_ID",
        "client_secret_env": "AI_OS_OAUTH_X_CLIENT_SECRET",
        "redirect_env": "AI_OS_OAUTH_X_REDIRECT_URI",
        "authorize": "https://x.com/i/oauth2/authorize",
        "token": "https://api.x.com/2/oauth2/token",
        "scopes": ["users.read", "tweet.read", "offline.access"],
        "token_mode": "pkce_form",
        "identity": "https://api.x.com/2/users/me",
    },
}

def _ensure_state_table() -> None:
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS social_oauth_states (
            state_hash TEXT PRIMARY KEY, business_id TEXT NOT NULL, provider TEXT NOT NULL,
            verifier_encrypted TEXT, created_at INTEGER NOT NULL)""")

def _config(provider: str) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Unsupported social provider.")
    spec = PROVIDERS[provider]
    values = {key: os.getenv(spec[key], "").strip() for key in
              ("client_id_env", "client_secret_env", "redirect_env")}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise OAuthError("OAuth app is not configured on the server yet. Missing: " +
                         ", ".join(spec[k] for k in missing))
    redirect = urllib.parse.urlsplit(values["redirect_env"])
    expected_path = "/business-integrations/social/" + provider + "/callback"
    if (redirect.scheme != "https" or not redirect.hostname or redirect.username or redirect.password
            or redirect.query or redirect.fragment or redirect.path.rstrip("/") != expected_path):
        raise OAuthError("Register the exact HTTPS callback path " + expected_path + " with this provider; do not add query strings or fragments.")
    return {"client_id": values["client_id_env"], "client_secret": values["client_secret_env"],
            "redirect_uri": values["redirect_env"]}

def readiness() -> list[dict]:
    result = []
    for provider, spec in PROVIDERS.items():
        try:
            _config(provider)
            _fernet()
            ready, reason = True, ""
        except (OAuthError, CredentialVaultUnavailable) as exc:
            ready, reason = False, str(exc)
        result.append({"provider": provider, "label": spec["label"], "app_configured": ready,
                       "status": "ready_to_authorize" if ready else "developer_app_setup_required",
                       "reason": reason, "read_only_scopes": spec["scopes"]})
    return result

def begin(provider: str, business_id: str) -> str:
    if business_id not in {"physical-agency", "physical-brand", "digital-products"}:
        raise ValueError("Choose one of the three business environments.")
    spec = PROVIDERS.get(provider)
    if not spec:
        raise ValueError("Unsupported social provider.")
    _fernet()  # fail before sending the owner to consent if token encryption is unavailable
    cfg = _config(provider)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64) if provider in {"x", "etsy"} else None
    params = {"client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"],
              "response_type": "code", "state": state, "scope": " ".join(spec["scopes"])}
    if provider == "meta":
        params["scope"] = ",".join(spec["scopes"])
    if provider == "tiktok":
        params["client_key"] = params.pop("client_id")
        params["scope"] = ",".join(spec["scopes"])
    if provider == "pinterest":
        params["scope"] = ",".join(spec["scopes"])
    if provider == "reddit":
        params.update({"duration": "permanent"})
    if provider in {"x", "etsy"}:
        params.update({"code_challenge": base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="),
            "code_challenge_method": "S256"})
    params.update(spec.get("extra_authorize", {}))
    _ensure_state_table()
    with connect() as db:
        db.execute("DELETE FROM social_oauth_states WHERE created_at < ?", (int(time.time()) - 900,))
        db.execute("INSERT INTO social_oauth_states(state_hash,business_id,provider,verifier_encrypted,created_at) VALUES(?,?,?,?,?)",
                   (hashlib.sha256(state.encode()).hexdigest(), business_id, provider,
                    _fernet().encrypt(verifier.encode()).decode("ascii") if verifier else None, int(time.time())))
    return spec["authorize"] + "?" + urllib.parse.urlencode(params)

def _request_json(url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={
        "Accept": "application/json", "User-Agent": "AIOS-social-oauth/1.0",
        **({"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}),
        **(headers or {}),
    }, method="POST" if body is not None else "GET")
    try:
        with urllib.request.build_opener(_SameOriginRedirect()).open(request, timeout=20) as response:
            raw = response.read(256001)
            if len(raw) > 256000:
                raise OAuthError("OAuth provider response exceeded the safe size limit.")
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise OAuthError("OAuth provider returned an unexpected response.")
            return value
    except urllib.error.HTTPError as exc:
        raise OAuthError("OAuth provider rejected the authorization exchange (HTTP " + str(exc.code) + ").") from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OAuthError("Could not complete OAuth provider exchange (" + type(exc).__name__ + ").") from exc

def verify_social_credential(provider: str, secret: str, config: dict, business_id: str) -> dict:
    """Verify a saved social OAuth token using a provider identity GET only.

    TikTok, Google/YouTube and Pinterest access tokens are refreshed when expired.
    Rotated refresh tokens are persisted immediately in the encrypted business vault.
    """
    if provider not in PROVIDERS or provider == "etsy":
        raise OAuthError("Unsupported social account test provider.")
    try:
        credential = json.loads(secret)
    except (TypeError, json.JSONDecodeError) as exc:
        raise OAuthError("Stored social token record is invalid; reconnect the account.") from exc
    access_token = credential.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise OAuthError("Stored social access token is missing; reconnect the account.")
    expires_at = credential.get("expires_at")
    refreshed = False
    if expires_at and int(time.time()) >= int(expires_at):
        refresh_token = credential.get("refresh_token")
        refreshable = {"tiktok", "youtube", "pinterest"}
        if provider not in refreshable or not refresh_token:
            raise OAuthError("Social access token expired; reconnect the account.")
        cfg = _config(provider)
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        headers = {}
        if provider == "tiktok":
            data.update({"client_key": cfg["client_id"], "client_secret": cfg["client_secret"]})
        elif provider == "youtube":
            data.update({"client_id": cfg["client_id"], "client_secret": cfg["client_secret"]})
        else:
            headers["Authorization"] = "Basic " + base64.b64encode((cfg["client_id"] + ":" + cfg["client_secret"]).encode()).decode()
        token = _request_json(PROVIDERS[provider]["token"], data, headers)
        new_access = token.get("access_token")
        lifetime = token.get("expires_in")
        if not isinstance(new_access, str) or not new_access or not lifetime:
            raise OAuthError("Provider refresh response was incomplete; reconnect the account.")
        credential.update({"access_token": new_access, "expires_at": int(time.time()) + int(lifetime),
                           "token_type": token.get("token_type", "Bearer"),
                           "scope": token.get("scope") or credential.get("scope")})
        if token.get("refresh_token"):
            credential["refresh_token"] = token["refresh_token"]
        if token.get("refresh_expires_in"):
            credential["refresh_expires_at"] = int(time.time()) + int(token["refresh_expires_in"])
        access_token = new_access
        refreshed = True
    headers = {"Authorization": "Bearer " + access_token}
    identity = _request_json(PROVIDERS[provider]["identity"], headers=headers)
    if provider == "tiktok":
        identity = identity.get("data", {}).get("user", {})
    elif provider == "youtube":
        items = identity.get("items") or []
        identity = items[0] if items else {}
    elif provider == "x":
        identity = identity.get("data", {})
    if not identity:
        raise OAuthError("Provider did not return a verifiable account identity; reconnect if access was revoked.")
    if provider == "meta":
        account = identity.get("name") or identity.get("id")
    elif provider == "youtube":
        account = (identity.get("snippet") or {}).get("title") or identity.get("id")
    else:
        account = identity.get("display_name") or identity.get("username") or identity.get("name") or identity.get("id") or identity.get("open_id")
    if not account:
        raise OAuthError("Provider identity response did not include an account label.")
    if refreshed:
        next_config = dict(config or {})
        next_config.update({"account": str(account)[:200], "identity": identity})
        save_business_integration(business_id, provider, json.dumps(credential), next_config)
    return {"provider": provider, "connected": True, "account": str(account)[:200],
            "token_refreshed": refreshed, "capability": "read-only account identity verification",
            "external_actions": "provider identity GET only; no publishing, messaging or account changes"}

def verify_etsy_credential(secret: str, config: dict, business_id: str | None = None) -> dict:
    """Verify an Etsy shop; refresh an expired access token using its stored refresh grant."""
    try:
        credential = json.loads(secret)
    except (TypeError, json.JSONDecodeError) as exc:
        raise OAuthError("Stored Etsy token record is invalid; reconnect the shop.") from exc
    access_token = credential.get("access_token")
    expires_at = credential.get("expires_at")
    api_key = (config or {}).get("etsy_api_key")
    shared_secret = (config or {}).get("etsy_shared_secret")
    if not access_token or not api_key or not shared_secret:
        raise OAuthError("Stored Etsy connection is incomplete; reconnect the shop.")
    if expires_at and int(time.time()) >= int(expires_at):
        refresh_token = credential.get("refresh_token")
        if not refresh_token:
            raise OAuthError("Etsy access token expired and no refresh token is stored. Reconnect the shop.")
        refreshed = _request_json(PROVIDERS["etsy"]["token"], {
            "grant_type": "refresh_token", "client_id": api_key,
            "refresh_token": refresh_token,
        })
        new_access = refreshed.get("access_token")
        new_refresh = refreshed.get("refresh_token") or refresh_token
        lifetime = refreshed.get("expires_in")
        if not isinstance(new_access, str) or not new_access or not lifetime:
            raise OAuthError("Etsy refresh grant returned an incomplete token response. Reconnect the shop.")
        credential.update({"access_token": new_access, "refresh_token": new_refresh,
                           "token_type": refreshed.get("token_type", "Bearer"),
                           "expires_at": int(time.time()) + int(lifetime),
                           "scope": refreshed.get("scope") or credential.get("scope")})
        access_token = new_access
        if business_id:
            save_business_integration(business_id, "etsy", json.dumps(credential), config)
    headers = {"Authorization": "Bearer " + access_token, "x-api-key": api_key + ":" + shared_secret}
    identity = _request_json("https://api.etsy.com/v3/application/users/me", headers=headers)
    shop_id = identity.get("shop_id")
    if not shop_id:
        raise OAuthError("Etsy did not return an owner shop for this account.")
    shop = _request_json("https://api.etsy.com/v3/application/shops/" + str(int(shop_id)), headers=headers)
    return {"provider": "etsy", "connected": True, "account": shop.get("shop_name") or "Etsy shop",
            "shop_id": shop_id, "token_refreshed": bool(expires_at and int(time.time()) < int(credential.get("expires_at") or 0)),
            "capability": "read-only Etsy shop access",
            "external_actions": "OAuth refresh and GET only; no listings, orders or shop settings changed"}


def complete(provider: str, state: str, code: str) -> dict:
    if provider not in PROVIDERS or not state or len(state) > 256 or not code or len(code) > 4096:
        raise ValueError("Invalid OAuth callback parameters.")
    _ensure_state_table()
    digest = hashlib.sha256(state.encode()).hexdigest()
    with connect() as db:
        row = db.execute("SELECT business_id,provider,verifier_encrypted,created_at FROM social_oauth_states WHERE state_hash=?",
                         (digest,)).fetchone()
        if row is None:
            raise OAuthError("OAuth state is invalid, expired, or already used. Start again from the owner dashboard.")
        db.execute("DELETE FROM social_oauth_states WHERE state_hash=?", (digest,))
    if row["provider"] != provider or int(time.time()) - row["created_at"] > 900:
        raise OAuthError("OAuth state did not match this provider or has expired.")
    cfg = _config(provider)
    spec = PROVIDERS[provider]
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": cfg["redirect_uri"]}
    headers = {}
    if provider == "tiktok":
        data.update({"client_key": cfg["client_id"], "client_secret": cfg["client_secret"]})
    elif provider == "meta":
        data.update({"client_id": cfg["client_id"], "client_secret": cfg["client_secret"]})
    elif provider == "x":
        data.update({"client_id": cfg["client_id"], "code_verifier": _fernet().decrypt(row["verifier_encrypted"].encode()).decode()})
        headers["Authorization"] = "Basic " + base64.b64encode(
            (cfg["client_id"] + ":" + cfg["client_secret"]).encode()).decode()
    elif provider == "etsy":
        data.update({"client_id": cfg["client_id"], "code_verifier": _fernet().decrypt(row["verifier_encrypted"].encode()).decode()})
    elif provider in {"pinterest", "reddit"}:
        if provider == "reddit":
            data["redirect_uri"] = cfg["redirect_uri"]
        headers["Authorization"] = "Basic " + base64.b64encode(
            (cfg["client_id"] + ":" + cfg["client_secret"]).encode()).decode()
    else:
        data.update({"client_id": cfg["client_id"], "client_secret": cfg["client_secret"]})
    token_url = spec["token"]
    if provider == "meta":
        token_url += "?" + urllib.parse.urlencode(data)
        token = _request_json(token_url)
    else:
        token = _request_json(token_url, data, headers)
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise OAuthError("OAuth exchange did not return an access token.")
    identity_headers = {"Authorization": "Bearer " + access_token}
    if provider == "etsy":
        identity_headers["x-api-key"] = cfg["client_id"] + ":" + cfg["client_secret"]
    if provider == "reddit":
        identity_headers["User-Agent"] = "AIOS/1.0 (owner-authorized account link)"
    identity = _request_json(spec["identity"], headers=identity_headers)
    if provider == "etsy":
        shop_id = identity.get("shop_id")
        if not shop_id:
            raise OAuthError("Etsy did not return a connected shop for this seller account.")
        identity["shop"] = _request_json("https://api.etsy.com/v3/application/shops/" + str(int(shop_id)), headers=identity_headers)
    if provider == "meta":
        pages = _request_json("https://graph.facebook.com/v24.0/me/accounts?fields=id,name,instagram_business_account{id,username}", headers=identity_headers)
        identity["pages"] = pages.get("data", [])
    if provider == "tiktok":
        identity = identity.get("data", {}).get("user", {})
    elif provider == "youtube":
        items = identity.get("items") or []
        identity = items[0] if items else {}
    elif provider == "x":
        identity = identity.get("data", {})
    elif provider == "meta":
        identity = identity
    if not identity:
        raise OAuthError("The provider did not return a verifiable account identity.")
    expires = token.get("expires_in")
    credential = json.dumps({"access_token": access_token,
        "refresh_token": token.get("refresh_token"),
        "token_type": token.get("token_type", "Bearer"),
        "expires_at": int(time.time()) + int(expires) if expires else None,
        "scope": token.get("scope") or token.get("scopes") or " ".join(spec["scopes"])})
    label = (identity.get("shop") or {}).get("shop_name") or identity.get("name") or identity.get("display_name") or identity.get("username") or identity.get("id") or identity.get("open_id") or "Verified account"
    save_business_integration(row["business_id"], provider, credential,
        {"account": str(label)[:200], "identity": identity, "connected_at": datetime.now(timezone.utc).isoformat(),
         "scopes": spec["scopes"], "read_only": True,
         **({"etsy_api_key": cfg["client_id"], "etsy_shared_secret": cfg["client_secret"]} if provider == "etsy" else {})})
    return {"business_id": row["business_id"], "provider": provider, "account": str(label)[:200],
            "connected": True, "token_expiry_seconds": expires, "read_only": True}
