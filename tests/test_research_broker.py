import json
from uuid import uuid4

from opencompany_core.domain import WorkItem
from opencompany_core.model_gateway import BillingMode, ModelGateway, ModelResult, ProviderPolicy
from opencompany_core.research_broker import ResearchBroker
from opencompany_core.workforce import default_workforce


class SelectionAdapter:
    def __init__(self, text):
        self.text = text
    def generate(self, request, *, model):
        return ModelResult(self.text, "unorouter", model, 0.0)


class FakeResearchClient:
    def __init__(self):
        self.calls = []
    def find_sites(self, query):
        return {"matches": [{"site": "hacker-news", "domain": "news.ycombinator.com"}]}
    def list_operations(self, site):
        return {"site": site, "operations": [
            {"name": "search", "readOnly": True, "minTier": 1, "summary": "Search public stories"},
            {"name": "submit", "readOnly": False, "minTier": 1, "summary": "Submit a story"},
            {"name": "browser_search", "readOnly": True, "minTier": 2, "summary": "Browser search"},
        ]}
    def call_read(self, site, operation, args, *, max_age_ms=0):
        self.calls.append((site, operation, args, max_age_ms))
        return {"ok": True, "class": "ok", "tier": 1, "data": [{"title": "SQLite"}]}


def make_gateway(text):
    return ModelGateway.configure(((
        ProviderPolicy("unorouter", "test/free-model:free", BillingMode.FREE_CONFIRMED, 0.0),
        SelectionAdapter(text),
    ),))


def make_item():
    return WorkItem(
        id=uuid4(), title="Research SQLite adoption",
        objective="Find public evidence about database adoption and current product trends.",
        department="intelligence-research",
    )


def test_research_broker_uses_only_confirmed_tier_one_read_operation():
    client = FakeResearchClient()
    gateway = make_gateway('{"site":"hacker-news","op":"search","args":{"query":"SQLite adoption"}}')
    broker = ResearchBroker(client, gateway)
    role = default_workforce().get("market_intelligence_analyst")
    outcome = broker.collect(role, make_item())
    assert outcome.reason == "read-only research completed"
    assert client.calls == [("hacker-news", "search", {"query": "SQLite adoption"}, 300000)]
    assert "SQLite" in outcome.result["bounded_json"]


def test_research_broker_rejects_sensitive_args_and_unlisted_operations():
    client = FakeResearchClient()
    gateway = make_gateway('{"site":"hacker-news","op":"search","args":{"email":"person@example.com"}}')
    broker = ResearchBroker(client, gateway)
    role = default_workforce().get("market_intelligence_analyst")
    outcome = broker.collect(role, make_item())
    assert "sensitive data" in outcome.reason
    assert client.calls == []

    bad_gateway = make_gateway('{"site":"hacker-news","op":"submit","args":{"title":"Hello"}}')
    outcome = ResearchBroker(client, bad_gateway).collect(role, make_item())
    assert "outside the read-only catalogue" in outcome.reason
    assert client.calls == []


def test_research_broker_skips_departments_without_research_scope():
    client = FakeResearchClient()
    role = default_workforce().get("python_platform_engineer")
    outcome = ResearchBroker(client, make_gateway("{}")).collect(role, make_item())
    assert outcome.result is None
    assert client.calls == []
