"""Shared test isolation defaults."""
import pytest


@pytest.fixture(autouse=True)
def disable_automatic_ceo_review_unless_a_test_opts_in(monkeypatch):
    # Prevent queued CEO reviews from one test consuming another test's worker job.
    # The end-to-end automation test opts in explicitly.
    monkeypatch.setenv("AI_OS_AUTO_CEO_REVIEW_ENABLED", "false")
