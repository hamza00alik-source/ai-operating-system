"""Owner-submitted, bounded public-web evidence capture for research tasks.

This is a read-only source collector, not a general browser. Redirect destinations
are revalidated, non-public DNS targets and non-text content are blocked. Responses
are stream-read with a strict byte cap; oversized pages are marked as partial.
"""
from __future__ import annotations

import html
import ipaddress
import socket
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from uuid import uuid4

from ai_os.db import connect

MAX_BYTES = 1_000_000
MAX_TEXT = 18_000
TIMEOUT = 12


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"} and self.skip:
            self.skip -= 1
        elif tag in {"p", "div", "article", "section", "li", "h1", "h2", "h3", "br"} and not self.skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def _clean_submitted_url(url: str) -> str:
    """Remove invisible formatting characters commonly introduced by copy/paste."""
    if not isinstance(url, str):
        raise ValueError("Enter a valid public HTTPS URL.")
    cleaned = unicodedata.normalize("NFC", url)
    cleaned = "".join(ch for ch in cleaned if unicodedata.category(ch) != "Cf")
    return cleaned.strip()


def _validate_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(_clean_submitted_url(url))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTPS URLs without embedded credentials are accepted.")
    if parsed.port not in (None, 443):
        raise ValueError("Only the standard HTTPS port is accepted.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost"} or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("Local and internal hostnames are blocked.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("The source hostname could not be resolved.") from exc
    if not addresses:
        raise ValueError("The source hostname has no public address.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Private, loopback, link-local and reserved network addresses are blocked.")
    return urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a few redirects, re-validating every destination before connecting."""

    max_redirects = 4

    def __init__(self):
        super().__init__()
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > self.max_redirects:
            raise ValueError("Source exceeded the 4-redirect safety limit.")
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_bounded(response, limit: int = MAX_BYTES) -> tuple[bytes, bool]:
    """Read at most limit bytes plus one sentinel byte to detect truncation."""
    raw = response.read(limit + 1)
    return raw[:limit], len(raw) > limit


def _add_redirect_provenance(text: str, submitted_url: str, final_url: str) -> str:
    """Keep redirect provenance attached to evidence seen by later research agents."""
    if submitted_url == final_url:
        return text
    note = (
        "[SOURCE REDIRECT WARNING: The owner submitted "
        f"{submitted_url} but the server redirected to {final_url}. "
        "The captured page may not be the intended evidence; verify relevance before use.]"
    )
    return note + "\\n\\n" + text


def capture_source(url: str) -> dict:
    submitted_url = _validate_url(url)
    safe_url = submitted_url
    redirect_handler = _SafeRedirect()
    request = urllib.request.Request(
        safe_url,
        headers={"User-Agent": "AIOS-ResearchEvidence/1.0 (+owner-triggered)", "Accept": "text/html,text/plain,application/xhtml+xml"},
    )
    opener = urllib.request.build_opener(redirect_handler)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            if response.status != 200:
                raise ValueError(f"Source returned HTTP {response.status}.")
            safe_url = _validate_url(response.geturl())
            content_type = response.headers.get("Content-Type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                raise ValueError("Only HTML and plain-text pages can be captured.")
            raw, truncated = _read_bounded(response)
            charset = response.headers.get_content_charset() or "utf-8"
            page = raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Source returned HTTP {exc.code}. The page may require a browser or block automated requests.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("Could not retrieve the source within the 12-second limit.") from exc

    if "html" in content_type:
        parser = _TextExtractor()
        parser.feed(page)
        text = html.unescape(" ".join(" ".join(parser.parts).split()))
    else:
        text = " ".join(page.split())
    text = text[:MAX_TEXT].strip()
    if truncated:
        text = (text + " [PARTIAL CAPTURE: source exceeded the 1 MB read limit; only the first 1 MB was inspected.]").strip()
    if len(text) < 120:
        raise ValueError("The page yielded too little readable text within the 1 MB capture limit.")
    title = ""
    if "html" in content_type:
        import re
        match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        if match:
            title = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", match.group(1))).split())[:300]
    redirected = safe_url != submitted_url
    text = _add_redirect_provenance(text, submitted_url, safe_url)
    source_id = str(uuid4())
    captured_at = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """INSERT INTO research_sources
            (id,url,title,content,captured_at,content_type)
            VALUES(?,?,?,?,?,?)""",
            (source_id, safe_url, title, text, captured_at, content_type[:120]),
        )
    return {
        "id": source_id,
        "url": safe_url,
        "submitted_url": submitted_url,
        "redirected": redirected,
        "redirect_count": redirect_handler.redirect_count,
        "redirect_warning": (
            "The submitted URL redirected to a different page. Review the final URL and page title; capture success does not establish that this is the intended evidence."
            if redirected else None
        ),
        "title": title,
        "captured_at": captured_at,
        "characters": len(text),
        "truncated": truncated,
        "bytes_captured": len(raw),
    }


def list_sources(limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    with connect() as db:
        rows = db.execute(
            "SELECT id,url,title,captured_at,content_type,length(content) AS characters FROM research_sources ORDER BY captured_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def research_context(query: str, limit: int = 8) -> str:
    terms = [term.casefold() for term in query.split() if len(term) > 3][:12]
    with connect() as db:
        rows = db.execute(
            "SELECT id,url,title,content,captured_at FROM research_sources ORDER BY captured_at DESC LIMIT 100"
        ).fetchall()
    scored = []
    for row in rows:
        haystack = (row["title"] + " " + row["content"]).casefold()
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: (item[0], item[1]["captured_at"]), reverse=True)
    selected = []
    for _, row in scored[:limit]:
        selected.append(
            f"Source URL: {row['url']}\nTitle: {row['title']}\nCaptured: {row['captured_at']}\nExtract: {row['content'][:3500]}"
        )
    return "\n\n---\n\n".join(selected)
