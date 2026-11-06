import json

import pytest
from pydantic import ValidationError

from ai_os.db import initialize_database
from ai_os.training_data import (
    create_training_example,
    export_training_dataset,
    list_training_dataset_exports,
    list_training_examples,
    review_training_example,
)
from ai_os.training_schemas import TrainingExampleCreate, TrainingExampleReview


@pytest.fixture
def training_db(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'training.db'}")
    initialize_database()


def _payload(**overrides):
    values = {
        "task_family": "research synthesis",
        "system_prompt": "You are a careful research analyst.",
        "user_input": "Summarize the supplied official release note.",
        "ideal_response": "The release added CSV export on 2026-10-29. Evidence: https://example.test/changelog",
        "source_refs": ["https://example.test/changelog"],
        "rights_confirmed": True,
        "privacy_reviewed": True,
    }
    values.update(overrides)
    return TrainingExampleCreate(**values)


def test_training_example_requires_owner_review_before_export(training_db):
    candidate = create_training_example(_payload(), actor="owner")
    assert candidate["status"] == "candidate"
    assert list_training_examples(status="accepted") == []
    with pytest.raises(ValueError, match="No owner-accepted"):
        export_training_dataset(actor="owner")
    accepted = review_training_example(
        candidate["id"], TrainingExampleReview(decision="accepted"), actor="owner"
    )
    assert accepted["status"] == "accepted"
    with pytest.raises(ValueError, match="already been reviewed"):
        review_training_example(
            candidate["id"], TrainingExampleReview(decision="rejected"), actor="owner"
        )


def test_dataset_export_is_deterministic_versioned_and_accepted_only(training_db):
    first = create_training_example(_payload(), actor="owner")
    second = create_training_example(
        _payload(task_family="customer support", user_input="Classify a generic support issue."),
        actor="owner",
    )
    review_training_example(first["id"], TrainingExampleReview(decision="accepted"), actor="owner")
    review_training_example(second["id"], TrainingExampleReview(decision="rejected"), actor="owner")
    exported = export_training_dataset(actor="owner")
    lines = exported["jsonl"].strip().splitlines()
    assert exported["version_number"] == 1
    assert exported["example_count"] == 1
    assert exported["example_ids"] == [first["id"]]
    record = json.loads(lines[0])
    assert record["messages"][2]["role"] == "assistant"
    assert record["metadata"]["example_id"] == first["id"]
    assert len(exported["dataset_sha256"]) == 64
    second_export = export_training_dataset(actor="owner")
    assert second_export["version_number"] == 2
    assert second_export["dataset_sha256"] == exported["dataset_sha256"]
    history = list_training_dataset_exports()
    assert len(history) == 2
    assert history[0]["version_number"] == 2


def test_training_candidates_require_rights_and_privacy_attestations(training_db):
    with pytest.raises(ValidationError, match="Rights and privacy"):
        _payload(privacy_reviewed=False)
    with pytest.raises(ValidationError, match="HTTPS"):
        _payload(source_refs=["http://example.test/source"])


def test_training_candidate_rejects_obvious_personal_email_or_secret(training_db):
    candidate = create_training_example(
        _payload(user_input="Use this customer email: person@example.com"),
        actor="owner",
    )
    # Schema validation is not a privacy scan; the storage layer rejects the content.
    with pytest.raises(ValueError, match="credential or personal email"):
        create_training_example(
            _payload(user_input="Use this customer email: person@example.com"),
            actor="owner",
        )
