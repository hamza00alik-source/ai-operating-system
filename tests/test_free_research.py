import xml.etree.ElementTree as ET

from ai_os import free_research


def test_feed_parser_matches_query_and_ignores_non_github_links(monkeypatch):
    xml = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>LangGraph durable execution update</title>
        <link href="https://github.com/langchain-ai/langgraph/releases/tag/v1"/>
        <updated>2026-11-01T00:00:00Z</updated><summary>New durable agent orchestration capabilities.</summary>
      </entry>
      <entry><title>Unrelated release</title>
        <link href="https://github.com/langchain-ai/langgraph/releases/tag/v2"/>
        <summary>Database driver improvements.</summary>
      </entry>
      <entry><title>Unsafe external link</title>
        <link href="https://example.com/release"/>
        <summary>Agent orchestration.</summary>
      </entry>
    </feed>"""
    monkeypatch.setattr(free_research, "_fetch_feed", lambda url: xml)
    monkeypatch.setattr(free_research, "FEEDS", (("LangGraph releases", "https://github.com/langchain-ai/langgraph/releases.atom"),))
    result = free_research.collect_release_feed_candidates("durable agent orchestration")
    assert len(result) == 1
    assert result[0]["url"] == "https://github.com/langchain-ai/langgraph/releases/tag/v1"
    assert result[0]["published_date"].startswith("2026-11-01")


def test_feed_fetch_rejects_non_allowlisted_host():
    import pytest
    with pytest.raises(free_research.FeedResearchError):
        free_research._fetch_feed("https://example.com/feed.atom")


def test_feed_query_requires_meaningful_term():
    import pytest
    with pytest.raises(ValueError):
        free_research.collect_release_feed_candidates("a and the")
