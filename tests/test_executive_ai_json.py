import json

import pytest

from opencompany_core.executive_ai import ExecutivePlanningError, _parse_model_json, create_executive_plan
from opencompany_core.model_gateway import BillingMode, ModelGateway, ModelResult, ProviderPolicy


VALID = '{"rationale":"Plan rationale","work_items":[]}'


def test_parse_plain_json_object():
    assert _parse_model_json(VALID) == {"rationale": "Plan rationale", "work_items": []}


def test_parse_json_markdown_fence():
    fence = chr(96) * 3
    assert _parse_model_json(fence + "json\n" + VALID + "\n" + fence) == {
        "rationale": "Plan rationale", "work_items": []
    }


def test_parse_json_with_short_preamble():
    assert _parse_model_json("Here is the requested plan:\n" + VALID) == {
        "rationale": "Plan rationale", "work_items": []
    }


@pytest.mark.parametrize("value", ["", "No JSON was returned", '{"rationale":', VALID + " " + VALID])
def test_reject_empty_malformed_or_multiple_payloads(value):
    with pytest.raises(ExecutivePlanningError):
        _parse_model_json(value)


def test_reject_non_object_json():
    with pytest.raises(ExecutivePlanningError):
        _parse_model_json('["not", "an", "object"]')


def test_ceo_plan_inherits_selected_business_unit():
    class PlanAdapter:
        def __init__(self):
            self.request = None

        def generate(self, request, *, model):
            self.request = request
            payload = {
                "rationale": "Keep this work inside the selected business.",
                "work_items": [{
                    "department": "intelligence-research",
                    "title": "Research agency buyers",
                    "objective": "Prepare a sourced international buyer report.",
                    "depends_on": [],
                }],
            }
            return ModelResult(json.dumps(payload), "unorouter", model, 0.0)

    adapter = PlanAdapter()
    gateway = ModelGateway.configure((
        (ProviderPolicy("unorouter", "test-model", BillingMode.FREE_CONFIRMED), adapter),
    ))
    plan = create_executive_plan(
        "Agency buyer research", "Find qualified international buyers.",
        gateway, business_id="physical-agency",
    )

    assert plan.work_items[0].business_id == "physical-agency"
    assert "Business unit: physical-agency" in adapter.request.prompt
    assert adapter.request.business_id == "physical-agency"
