import pytest

from opencompany_core.executive_ai import ExecutivePlanningError, _parse_model_json


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
