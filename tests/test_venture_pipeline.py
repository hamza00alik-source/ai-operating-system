from ai_os.venture_pipeline import DIMENSIONS, build_financial_scenarios, clean_evidence_records, score_assessment


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
        {"url": "https://example.com/report", "claim": "Demand evidence", "owner_verified": True},
        {"url": "https://example.com/report/", "claim": "Duplicate", "owner_verified": True},
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
        {"url": "https://example.com/a", "owner_verified": True},
        {"url": "https://example.com/b", "owner_verified": True},
    ])
    result = score_assessment({
        "ratings": {dimension: 3 for dimension in DIMENSIONS},
        "source_urls": [item["url"] for item in evidence],
    })
    assert result["source_count"] == 2



def test_financial_scenarios_calculate_profit_and_break_even_from_explicit_inputs():
    assumptions = {
        "monthly_sales": 20,
        "average_price": 100,
        "variable_cost_per_sale": 40,
        "monthly_fixed_cost": 500,
        "monthly_marketing_cost": 100,
        "startup_cost": 300,
    }
    result = build_financial_scenarios({
        "conservative": assumptions,
        "base": assumptions,
        "upside": assumptions,
    })
    base = result["scenarios"]["base"]
    assert base["monthly_revenue"] == 2000
    assert base["monthly_operating_profit_before_tax"] == 600
    assert base["break_even_sales_per_month"] == 10
    assert base["first_month_net_cash_after_startup"] == 300


def test_financial_scenarios_reject_missing_or_loss_making_unit_economics():
    assumptions = {
        "monthly_sales": 10,
        "average_price": 20,
        "variable_cost_per_sale": 20,
        "monthly_fixed_cost": 0,
        "monthly_marketing_cost": 0,
        "startup_cost": 0,
    }
    try:
        build_financial_scenarios({
            "conservative": assumptions, "base": assumptions, "upside": assumptions,
        })
    except ValueError as exc:
        assert "positive contribution" in str(exc)
    else:
        raise AssertionError("Loss-making unit economics must be rejected")


def test_unreviewed_https_candidates_do_not_count_as_launch_evidence():
    evidence = clean_evidence_records([
        {"url": "https://example.com/candidate"},
        {"url": "https://example.org/reviewed", "owner_verified": True},
    ])
    assert len(evidence) == 2
    verified = [item["url"] for item in evidence if item["owner_verified"]]
    result = score_assessment({
        "ratings": {dimension: 3 for dimension in DIMENSIONS},
        "source_urls": verified,
    })
    assert result["source_count"] == 1
