"""Opt-in Exa web research adapter.

This adapter is deliberately disabled by default. Exa search is a metered
external service; callers must explicitly enable it in the private runtime.
Search results are stored as unreviewed knowledge candidates, never trusted facts.
"""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ResearchNotConfigured(RuntimeError):
    pass


class ResearchProviderError(RuntimeError):
    pass


def research_status() -> dict:
    enabled = os.getenv("AI_OS_RESEARCH_ENABLED", "false").strip().lower() == "true"
    configured = bool(os.getenv("EXA_API_KEY", "").strip())
    return {
        "provider": "exa",
        "enabled": enabled and configured,
        "configured": configured,
        "requires_paid_service": True,
        "notice": (
            "Metered Exa search is enabled."
            if enabled and configured
            else "Disabled by default. No external search or charge will occur."
        ),
    }


def search_exa(query: str, *, num_results: int = 5) -> list[dict]:
    """Perform one bounded Exa search; no retries or hidden fallback are made."""
    status = research_status()
    if not status["enabled"]:
        raise ResearchNotConfigured(
            "Research is disabled. Configure AI_OS_RESEARCH_ENABLED=true and EXA_API_KEY "
            "only after approving metered search costs."
        )
    if not 1 <= num_results <= 5:
        raise ValueError("num_results must be between 1 and 5")
    payload = json.dumps({
        "query": query,
        "type": "auto",
        "numResults": num_results,
        "contents": {"highlights": True},
    }).encode("utf-8")
    request = Request(
        "https://api.exa.ai/search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": os.environ["EXA_API_KEY"],
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read(2_000_000).decode("utf-8"))
    except HTTPError as exc:
        raise ResearchProviderError(f"Research provider returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, OSError):
        raise ResearchProviderError("Research provider could not be reached.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ResearchProviderError("Research provider returned invalid JSON.") from None

    results = data.get("results", [])
    if not isinstance(results, list):
        raise ResearchProviderError("Research provider response had an invalid results field.")
    normalized = []
    for result in results[:num_results]:
        if not isinstance(result, dict):
            continue
        url = result.get("url")
        title = result.get("title")
        highlights = result.get("highlights", [])
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(highlights, list):
            highlights = []
        excerpt = "\n\n".join(
            item.strip() for item in highlights
            if isinstance(item, str) and item.strip()
        )[:8000]
        if not excerpt:
            continue
        normalized.append({
            "url": url,
            "title": title.strip()[:200],
            "published_date": result.get("publishedDate"),
            "excerpt": excerpt,
        })
    return normalized
