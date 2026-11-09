import pytest

from ai_os.agent_runtime import _extract_tool_proposal


def test_extracts_exact_single_line_proposal_with_nested_arguments():
    response = """Research notes first.
AIOS_TOOL_PROPOSAL: {"server_id":"research-mcp","tool_name":"search","arguments":{"query":"market","filters":{"region":"global"}}}
"""
    assert _extract_tool_proposal(response) == {
        "server_id": "research-mcp",
        "tool_name": "search",
        "arguments": {"query": "market", "filters": {"region": "global"}},
    }


def test_ignores_response_without_explicit_proposal_marker():
    assert _extract_tool_proposal("No external lookup is required.") is None


def test_rejects_multiple_proposal_markers():
    response = (
        'AIOS_TOOL_PROPOSAL: {"server_id":"a","tool_name":"search","arguments":{}}\n'
        'AIOS_TOOL_PROPOSAL: {"server_id":"b","tool_name":"search","arguments":{}}'
    )
    with pytest.raises(ValueError, match="Only one"):
        _extract_tool_proposal(response)


def test_rejects_unknown_proposal_fields():
    response = 'AIOS_TOOL_PROPOSAL: {"server_id":"a","tool_name":"search","arguments":{},"execute":true}'
    with pytest.raises(ValueError, match="exactly"):
        _extract_tool_proposal(response)


def test_rejects_non_object_arguments():
    response = 'AIOS_TOOL_PROPOSAL: {"server_id":"a","tool_name":"search","arguments":[]}'
    with pytest.raises(ValueError, match="JSON object"):
        _extract_tool_proposal(response)
