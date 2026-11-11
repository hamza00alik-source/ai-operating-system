from ai_os.venture_pipeline import DIMENSIONS, score_assessment


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
