import socket

import pytest

from ai_os import research_sources


def test_validate_url_rejects_non_https_and_nonstandard_ports():
    with pytest.raises(ValueError):
        research_sources._validate_url("http://example.com/report")
    with pytest.raises(ValueError):
        research_sources._validate_url("https://example.com:8443/report")


def test_validate_url_rejects_private_dns_results(monkeypatch):
    monkeypatch.setattr(
        research_sources.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="Private"):
        research_sources._validate_url("https://example.com/report")


def test_validate_url_accepts_public_https_host(monkeypatch):
    monkeypatch.setattr(
        research_sources.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    assert research_sources._validate_url("https://example.com/report?q=1") == "https://example.com/report?q=1"


def test_text_extractor_skips_script_and_navigation():
    parser = research_sources._TextExtractor()
    parser.feed("<html><body><nav>Menu</nav><article><h1>Market report</h1><p>Useful evidence</p><script>secret()</script></article></body></html>")
    extracted = " ".join(" ".join(parser.parts).split())
    assert "Market report" in extracted
    assert "Useful evidence" in extracted
    assert "Menu" not in extracted
    assert "secret" not in extracted


def test_validate_url_strips_invisible_word_joiner(monkeypatch):
    monkeypatch.setattr(
        research_sources.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    submitted = "https://store.steampowered.com/hwsurvey\u2060/"
    assert research_sources._validate_url(submitted) == "https://store.steampowered.com/hwsurvey/"
