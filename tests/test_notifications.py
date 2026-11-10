import pytest

from ai_os import notifications


@pytest.fixture
def notification_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'notifications.db'}")
    from ai_os.db import initialize_database
    initialize_database()
    return True


def test_internal_notification_is_queued_without_sending(notification_db):
    item = notifications.enqueue_notification(title="Worker alert", body="Worker stopped.")
    assert item["audience"] == "internal"
    assert item["status"] == "queued"
    assert item["attempts"] == 0


def test_customer_notification_requires_approved_owner_record(notification_db):
    from ai_os.db import connect

    with connect() as db:
        db.execute(
            "INSERT INTO approvals(id,task_id,action,details,status,created_at) "
            "VALUES('approval-1',NULL,'send_customer_message','test','pending','2026-01-01T00:00:00Z')"
        )
    item = notifications.enqueue_notification(
        title="Order update", body="Your order is ready.", audience="customer",
        approval_id="approval-1",
    )
    assert item["status"] == "pending_approval"
    with pytest.raises(PermissionError):
        notifications.approve_notification(item["id"])

    with connect() as db:
        db.execute("UPDATE approvals SET status='approved' WHERE id='approval-1'")
    approved = notifications.approve_notification(item["id"])
    assert approved["status"] == "queued"


def test_delivery_is_disabled_by_default(notification_db, monkeypatch):
    item = notifications.enqueue_notification(title="Alert", body="Check queue.")
    monkeypatch.delenv("AI_OS_NOTIFICATIONS_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="disabled"):
        notifications.deliver_notification(item["id"])
