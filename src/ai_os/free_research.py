"""Free, bounded release-feed research from a fixed public-source allowlist.

No search key or paid provider is used. The endpoint is owner-initiated;
feed entries are untrusted candidates and are never treated as instructions.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlparse
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET


class FeedResearchError(RuntimeError):
    pass


FEEDS = (
    ("LangGraph releases", "https://github.com/langchain-ai/langgraph/releases.atom"),
    ("CrewAI releases", "https://github.com/crewAIInc/crewAI/releases.atom"),
    ("Prefect releases", "https://github.com/PrefectHQ/prefect/releases.atom"),
    ("FastAPI releases", "https://github.com/fastapi/fastapi/releases.atom"),
    ("WooCommerce releases", "https://github.com/woocommerce/woocommerce/releases.atom"),
    ("WordPress releases", "https://github.com/WordPress/wordpress-develop/releases.atom"),
)
ATOM = "{http://www.w3.org/2005/Atom}"
MAX_FEED_BYTES = 1_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _public_github_host(host: str) -> bool:
    if host != "github.com":
        return False
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            return False
    return bool(addresses)


def _date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _fetch_feed(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password:
        raise FeedResearchError("Feed URL is not on the fixed HTTPS source allowlist.")
    if not _public_github_host(parsed.hostname):
        raise FeedResearchError("The approved feed host did not resolve to public addresses.")
    request = Request(url, headers={"User-Agent": "AI-Operating-System-Research/0.1", "Accept": "application/atom+xml, application/xml"})
    opener = build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=12) as response:
            if response.geturl() != url or response.status != 200:
                raise FeedResearchError("Feed server returned an unexpected response.")
            payload = response.read(MAX_FEED_BYTES + 1)
    except HTTPError:
        raise FeedResearchError("An approved release feed could not be fetched.") from None
    except (URLError, TimeoutError, OSError):
        raise FeedResearchError("An approved release feed could not be reached.") from None
    if len(payload) > MAX_FEED_BYTES:
        raise FeedResearchError("Feed exceeded the one-megabyte safety limit.")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise FeedResearchError("Feed contained a prohibited XML declaration.")
    return payload


def collect_release_feed_candidates(query: str, *, max_per_feed: int = 5) -> list[dict]:
    """Collect query-matching entries from six fixed release feeds, max 30 results."""
    if not 1 <= max_per_feed <= 5:
        raise ValueError("max_per_feed must be between 1 and 5")
    terms = {
        term for term in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", query.lower())
        if term not in {"the", "and", "for", "with", "from", "that", "this"}
    }
    if not terms:
        raise ValueError("Research query must contain at least one meaningful search term.")
    output = []
    for source_title, url in FEEDS:
        try:
            root = ET.fromstring(_fetch_feed(url))
        except (ET.ParseError, FeedResearchError):
            continue
        entries = root.findall(f"{ATOM}entry")
        for entry in entries[:max_per_feed]:
            title = _text(entry.find(f"{ATOM}title"))
            summary = _text(entry.find(f"{ATOM}summary")) or _text(entry.find(f"{ATOM}content"))
            link_element = next((item for item in entry.findall(f"{ATOM}link")
                                 if item.attrib.get("rel", "alternate") == "alternate"), None)
            link = link_element.attrib.get("href", "") if link_element is not None else ""
            parsed_link = urlparse(link)
            if parsed_link.scheme != "https" or parsed_link.hostname != "github.com":
                continue
            haystack = (title + " " + summary + " " + source_title).lower()
            matches = len(terms & set(re.findall(r"[a-z0-9][a-z0-9_-]{2,}", haystack)))
            if not title or not summary or matches == 0:
                continue
            published = _date(_text(entry.find(f"{ATOM}published")) or _text(entry.find(f"{ATOM}updated")))
            output.append({
                "url": link,
                "title": title[:200],
                "published_date": published,
                "excerpt": summary[:8000],
                "source_title": source_title,
                "match_terms": matches,
            })
    output.sort(key=lambda item: (item["match_terms"], item["published_date"] or ""), reverse=True)
    deduped, seen = [], set()
    for item in output:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)
    return deduped[:30]
