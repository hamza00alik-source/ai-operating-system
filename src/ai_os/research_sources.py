"""Owner-submitted, bounded public-web evidence capture for research tasks.

This is a read-only source collector, not a general browser. It blocks redirects,
non-public DNS targets, oversized responses, non-text content, and private-network URLs.
"""
from __future__ import annotations

import html
import ipaddress
import json
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def capture_source(url: str) -> dict:
    safe_url = _validate_url(url)
    request = urllib.request.Request(
        safe_url,
        headers={"User-Agent": "AIOS-ResearchEvidence/1.0 (+owner-triggered)", "Accept": "text/html,text/plain,application/xhtml+xml"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            if response.status != 200:
                raise ValueError(f"Source returned HTTP {response.status}; redirects are not followed.")
            content_type = response.headers.get("Content-Type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                raise ValueError("Only HTML and plain-text pages can be captured.")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Source exceeds the 1 MB capture limit.")
            charset = response.headers.get_content_charset() or "utf-8"
            page = raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Source returned HTTP {exc.code}; redirects are not followed.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("Could not retrieve the source within the 12-second limit.") from exc

    if "html" in content_type:
        parser = _TextExtractor()
        parser.feed(page)
        text = html.unescape(" ".join(" ".join(parser.parts).split()))
    else:
        text = " ".join(page.split())
    text = text[:MAX_TEXT].strip()
    if len(text) < 120:
        raise ValueError("The page yielded too little readable text to be useful.")
    title = ""
    if "html" in content_type:
        import re
        match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        if match:
            title = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", match.group(1))).split())[:300]
    source_id = str(uuid4())
    captured_at = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """INSERT INTO research_sources
            (id,url,title,content,captured_at,content_type)
            VALUES(?,?,?,?,?,?)""",
            (source_id, safe_url, title, text, captured_at, content_type[:120]),
        )
    return {"id": source_id, "url": safe_url, "title": title, "captured_at": captured_at, "characters": len(text)}


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
