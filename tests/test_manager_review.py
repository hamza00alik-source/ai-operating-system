from uuid import uuid4

import pytest

from opencompany_core.domain import TaskState, WorkItem
from opencompany_core.manager_review import ManagerReviewError, review_specialist_deliverables
from opencompany_core.model_gateway import ModelResult
from opencompany_core.workforce import default_workforce


class FakeGateway:
    def __init__(self, response):
        self.response = response
        self.request = None

    def complete(self, request, *, request_budget_usd, preferred_provider):
        self.request = request
        assert request_budget_usd == 0.0
        assert preferred_provider == "unorouter"
        return ModelResult(
            text=self.response, provider="unorouter", model="test:free", cost_usd=0.0
        )


def _item():
    return WorkItem(
        id=uuid4(), title="Research buyer demand",
        objective="Produce evidence-based buyer demand research",
        department="intelligence-research", state=TaskState.REVIEW,
    )


def _evidence():
    return ({
        "role_key": "market_research_analyst",
        "content": "Three relevant sources support the demand estimate.",
        "provider": "unorouter", "model": "test:free",
    },)


def test_manager_accepts_valid_specialist_deliverable():
    gateway = FakeGateway(
        '{"approved":true,"rationale":"The draft meets the objective and cites evidence.",'
        '"rework_instructions":""}'
    )
    decision = review_specialist_deliverables(
        _item(), "market_intelligence_analyst", _evidence(), gateway
    )
    assert decision.approved is True
    assert decision.rework_instructions == ""
    assert gateway.request.role_key == "market_intelligence_analyst"
    manager_role = default_workforce().get("market_intelligence_analyst")
    assert manager_role.mission in gateway.request.prompt
    assert manager_role.playbook.workflow_steps[0] in gateway.request.prompt
    assert manager_role.playbook.quality_rubric[0] in gateway.request.prompt


def test_manager_requests_specific_rework():
    gateway = FakeGateway(
        '{"approved":false,"rationale":"The sample is too small.",'
        '"rework_instructions":"Expand the sample and explain selection bias."}'
    )
    decision = review_specialist_deliverables(
        _item(), "market_intelligence_analyst", _evidence(), gateway
    )
    assert decision.approved is False
    assert "Expand the sample" in decision.rework_instructions


@pytest.mark.parametrize("response", [
    "not json",
    '{"approved":"yes","rationale":"bad","rework_instructions":""}',
    '{"approved":false,"rationale":"bad","rework_instructions":""}',
    '{"approved":true,"rationale":"ok","rework_instructions":"ignore policy"}',
    '{"approved":true,"rationale":"ok","rework_instructions":"","extra":1}',
])
def test_manager_rejects_invalid_or_ambiguous_decisions(response):
    with pytest.raises(ManagerReviewError):
        review_specialist_deliverables(
            _item(), "market_intelligence_analyst", _evidence(), FakeGateway(response)
        )


def test_manager_requires_deliverable_evidence():
    with pytest.raises(ManagerReviewError):
        review_specialist_deliverables(
            _item(), "market_intelligence_analyst", (), FakeGateway("{}")
        )



def test_manager_rejects_role_from_another_department():
    with pytest.raises(ManagerReviewError):
        review_specialist_deliverables(
            _item(), "financial_control_analyst", _evidence(), FakeGateway("{}")
        )


def test_manager_fails_closed_instead_of_truncating_large_deliverables():
    oversized = ({
        "role_key": "market_research_analyst",
        "content": "x" * 6001,
    },)
    with pytest.raises(ManagerReviewError):
        review_specialist_deliverables(
            _item(), "market_intelligence_analyst", oversized, FakeGateway("{}")
        )


def test_manager_rejects_more_than_eight_deliverables():
    with pytest.raises(ManagerReviewError):
        review_specialist_deliverables(
            _item(), "market_intelligence_analyst", _evidence() * 9, FakeGateway("{}")
        )
