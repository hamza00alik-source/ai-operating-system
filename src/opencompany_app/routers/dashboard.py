"""Owner dashboard HTTP route, isolated from the API composition root."""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from opencompany_app.dashboard import OWNER_DASHBOARD_HTML
from opencompany_app.provider_settings_ui import OWNER_PROVIDER_SETTINGS_HTML, OWNER_PROVIDER_SETTINGS_JS
from opencompany_app.product_rd_ui import PRODUCT_RD_HTML, PRODUCT_RD_JS
from opencompany_app.approval_inbox_ui import APPROVAL_INBOX_HTML, APPROVAL_INBOX_JS

router = APIRouter()


@router.get("/owner", response_class=HTMLResponse)
def owner_dashboard() -> HTMLResponse:
    html = OWNER_DASHBOARD_HTML.replace("</main>", OWNER_PROVIDER_SETTINGS_HTML + APPROVAL_INBOX_HTML + PRODUCT_RD_HTML + "\n</main>")
    before, marker, after = html.rpartition("})();")
    if marker:
        html = before + OWNER_PROVIDER_SETTINGS_JS + APPROVAL_INBOX_JS + PRODUCT_RD_JS + "\n  const previousLoad=load; load=async function(){await previousLoad(); await loadUnoRouterSettings(); await loadGitHubEvolutionSettings(); await loadModelUsage(); await loadProductRD(); await loadCompanyApprovalInbox();};\n})();" + after
    # The dashboard currently embeds its scripts. Give every script element a
    # fresh nonce rather than allowing arbitrary inline script execution.
    nonce = secrets.token_urlsafe(18)
    html = re.sub(r"<script(?=[\s>])", f'<script nonce="{nonce}"', html)
    html = re.sub(r"<style(?=[\s>])", f'<style nonce="{nonce}"', html)
    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'nonce-{nonce}'; connect-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'; object-src 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response
