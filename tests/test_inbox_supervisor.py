import json

import pytest

from ai_os.inbox_supervisor import _parse_decision


def test_parse_internal_task_decision():
    decision = _parse_decision(json.dumps({
        "action": "create_task",
        "title": "Review supplier quote",
        "description": "Compare the quoted specifications and identify missing evidence.",
    }))
    assert decision["action"] == "create_task"
    assert decision["title"] == "Review supplier quote"


def test_parse_no_action_decision():
    assert _parse_decision('{"action":"no_action","reason":"Informational handoff"}')["action"] == "no_action"


@pytest.mark.parametrize("response", [
    "not json",
    '{"action":"publish"}',
    '{"action":"create_task","title":"","description":"x"}',
    '{"action":"create_task","title":"x","description":""}',
])
def test_reject_invalid_or_external_decisions(response):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        _parse_decision(response)
