import sqlite3
from threading import RLock
from uuid import uuid4

import pytest

from opencompany_core.model_usage import ModelUsageRepository


def event(**overrides):
    value = {
        "request_id": str(uuid4()),
        "work_item_id": str(uuid4()),
        "role_key": "market_intelligence_analyst",
        "provider": "unorouter",
        "model": "vendor/free-model:free",
        "input_tokens": 120,
        "output_tokens": 45,
        "cost_usd": 0.0,
    }
    value.update(overrides)
    return value


def test_usage_repository_records_and_summarizes_cost_and_tokens():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    repository = ModelUsageRepository(connection, RLock())
    assert repository.record(event()) is True
    summary = repository.summary()
    assert summary["request_count"] == 1
    assert summary["total_cost_usd"] == 0.0
    assert summary["total_input_tokens"] == 120
    assert summary["total_output_tokens"] == 45
    connection.close()


def test_usage_repository_is_idempotent_for_matching_request_id():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    repository = ModelUsageRepository(connection, RLock())
    record = event()
    assert repository.record(record) is True
    assert repository.record(record) is False
    assert repository.summary()["request_count"] == 1
    connection.close()


def test_usage_repository_rejects_accounting_conflicts_and_invalid_cost():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    repository = ModelUsageRepository(connection, RLock())
    record = event()
    repository.record(record)
    with pytest.raises(ValueError, match="different accounting"):
        repository.record({**record, "cost_usd": 0.01})
    with pytest.raises(ValueError, match="finite and non-negative"):
        repository.record(event(cost_usd=float("nan")))
    connection.close()
