"""Coverage for model-originated, approval-only worker intents."""
from opencompany_core.worker_runner import OpenCompanyWorker


def test_worker_extracts_one_bounded_approval_block_and_cleans_deliverable():
    raw = (
        "Analysis draft.\\n<OPENCOMPANY_APPROVAL_REQUESTS>\\n"
        '[{"action_type":"publish_listing","title":"Publish draft listing",'
        '"description":"Publish only after owner approval."}]'
        "\\n</OPENCOMPANY_APPROVAL_REQUESTS>"
    )
    requests, cleaned = OpenCompanyWorker._extract_approval_requests(raw)
    assert len(requests) == 1
    assert requests[0]["action_type"] == "publish_listing"
    assert "OPENCOMPANY_APPROVAL_REQUESTS" not in cleaned
    assert cleaned == "Analysis draft."


def test_worker_rejects_unknown_fields_and_invalid_action_types():
    unknown = '<OPENCOMPANY_APPROVAL_REQUESTS>[{"action_type":"payment","title":"Pay","description":"x","api_key":"secret"}]</OPENCOMPANY_APPROVAL_REQUESTS>'
    invalid = '<OPENCOMPANY_APPROVAL_REQUESTS>[{"action_type":"run_shell","title":"Run","description":"x"}]</OPENCOMPANY_APPROVAL_REQUESTS>'
    assert OpenCompanyWorker._extract_approval_requests(unknown) == ([], unknown)
    assert OpenCompanyWorker._extract_approval_requests(invalid) == ([], invalid)


def test_worker_rejects_multiple_blocks_and_more_than_five_requests():
    one = '<OPENCOMPANY_APPROVAL_REQUESTS>[]</OPENCOMPANY_APPROVAL_REQUESTS>'
    assert OpenCompanyWorker._extract_approval_requests(one + one) == ([], one + one)
    six = [{"action_type":"other","title":"x","description":"y"} for _ in range(6)]
    import json
    too_many = "<OPENCOMPANY_APPROVAL_REQUESTS>" + json.dumps(six) + "</OPENCOMPANY_APPROVAL_REQUESTS>"
    assert OpenCompanyWorker._extract_approval_requests(too_many) == ([], too_many)
