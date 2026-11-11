from ai_os.venture_pipeline import DIMENSIONS, clean_evidence_records, score_assessment


def test_venture_score_is_not_created_from_incomplete_ratings():
    result = score_assessment({"ratings": {"demand": 5, "economics": 4}})
    assert result["score"] is None
    assert result["coverage"] == 2
    assert result["label"] == "incomplete_assessment"


def test_venture_score_requires_all_six_explicit_ratings():
    result = score_assessment({
        "ratings": {dimension: 3 for dimension in DIMENSIONS},
        "source_urls": ["https://example.com/source-1", "https://example.com/source-2"],
    })
    assert result["score"] == 60
    assert result["coverage"] == 6
    assert result["source_count"] == 2
    assert result["label"] == "provisional_research_score"


def test_non_https_sources_do_not_count_toward_launch_evidence():
    result = score_assessment({
        "ratings": {dimension: 4 for dimension in DIMENSIONS},
        "source_urls": ["http://example.com", "javascript:alert(1)", "https://example.com/real"],
    })
    assert result["source_count"] == 1
    assert result["score"] == 80
    assert "not independently verified" in result["warning"]

def test_boolean_values_are_not_accepted_as_ratings():
    result = score_assessment({
        "ratings": {dimension: 4 for dimension in DIMENSIONS} | {"demand": True},
        "source_urls": ["https://example.com/one", "https://example.com/two", "https://example.com/three"],
    })
    assert result["score"] is None
    assert result["coverage"] == 5



def test_evidence_candidates_require_https_host_and_are_deduplicated():
    evidence = clean_evidence_records([
        {"url": "https://example.com/report", "claim": "Demand evidence"},
        {"url": "https://example.com/report/", "claim": "Duplicate"},
        {"url": "http://example.com/insecure"},
        {"url": "https:///missing-host"},
        {"url": "https://user:pass@example.com/private"},
        {"url": "javascript:alert(1)"},
    ])
    assert [item["url"] for item in evidence] == ["https://example.com/report"]


def test_assessment_source_count_uses_only_normalized_evidence_records():
    # Arbitrary URLs supplied in assessment JSON are overwritten by save_assessment
    # with this normalized evidence list before score_assessment is called.
    evidence = clean_evidence_records([
        {"url": "https://example.com/a"},
        {"url": "https://example.com/b"},
    ])
    result = score_assessment({
        "ratings": {dimension: 3 for dimension in DIMENSIONS},
        "source_urls": [item["url"] for item in evidence],
    })
    assert result["source_count"] == 2
