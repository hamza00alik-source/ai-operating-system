from datetime import datetime, timezone
from uuid import uuid4
import pytest
import hashlib
from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_core.business_units import BusinessUnitRegistry
from opencompany_core.business_assets import BusinessAssetRegistry


def audit(actor_type="owner"):
    return AuditRecord(id=uuid4(),occurred_at=datetime.now(timezone.utc),
        actor_type=actor_type,actor_id="owner",action="business.asset_declared",
        subject_type="business_asset",subject_id="test",outcome="pending_storage",
        correlation_id=str(uuid4()),details={})


def expected_storage_key(business_id, declared):
    prefix=hashlib.sha256((business_id+"\\0"+declared["asset_scope_id"]).encode("utf-8")).hexdigest()
    return prefix+"/"+declared["asset_id"]+".blob"


def declare(registry,business_id="physical-agency",asset_key="hero-model",audit_record=None):
    return registry.declare(business_id,asset_key=asset_key,title="Hero model",
        asset_type="3d-model",filename="hero.glb",media_type="model/gltf-binary",
        checksum_sha256="a"*64,byte_size=1024,source="owner asset manifest",
        audit=audit_record or audit())


def test_asset_metadata_isolated_between_business_units(tmp_path):
    store=SQLiteStore(tmp_path/"assets.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    declared=declare(assets)
    assert declared["storage_state"]=="metadata_only"
    assert declared["file_bytes_received"] is False
    assert len(assets.list("physical-agency"))==1
    assert assets.list("physical-brand")==()
    events=assets.events("physical-agency",declared["asset_id"])
    assert len(events)==1 and events[0]["action"]=="declared"
    assert assets.events("physical-brand",declared["asset_id"])==()
    store.close()


def test_asset_registry_rejects_paths_invalid_hash_and_non_owner(tmp_path):
    store=SQLiteStore(tmp_path/"assets.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    with pytest.raises(ValueError):
        assets.declare("physical-agency",asset_key="bad",title="Bad",asset_type="3d-model",
            filename="../secret.glb",media_type="model/gltf-binary",checksum_sha256="a"*64,
            byte_size=12,source="manifest",audit=audit())
    with pytest.raises(ValueError):
        assets.declare("physical-agency",asset_key="bad",title="Bad",asset_type="3d-model",
            filename="bad.glb",media_type="model/gltf-binary",checksum_sha256="not-a-hash",
            byte_size=12,source="manifest",audit=audit())
    with pytest.raises(PermissionError):
        assets.declare("physical-agency",asset_key="bad",title="Bad",asset_type="3d-model",
            filename="bad.glb",media_type="model/gltf-binary",checksum_sha256="a"*64,
            byte_size=12,source="manifest",audit=audit("agent"))
    store.close()


def test_asset_declarations_and_history_are_append_only(tmp_path):
    store=SQLiteStore(tmp_path/"assets.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    declare(assets)
    with pytest.raises(Exception):
        store._connection.execute("DELETE FROM opencompany_business_assets")
    with pytest.raises(Exception):
        store._connection.execute("DELETE FROM opencompany_business_asset_events")
    store.close()


def test_verified_storage_lifecycle_is_business_scoped_and_not_downloadable(tmp_path):
    store=SQLiteStore(tmp_path/"asset-storage-lifecycle.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    declared=declare(assets)
    declaration=assets.storage_declaration("physical-agency",declared["asset_id"])
    assert declaration["asset_scope_id"]
    result=assets.record_storage(
        "physical-agency",declared["asset_id"],
        storage_key=expected_storage_key("physical-agency",declared),
        checksum_sha256=declared["checksum_sha256"],byte_size=declared["byte_size"],
        audit=audit(),
    )
    assert result["status"]=="pending_scan"
    assert result["download_enabled"] is False
    listed=assets.list("physical-agency")[0]
    assert listed["storage_state"]=="private_stored_unscanned"
    assert listed["status"]=="pending_scan"
    history=assets.events("physical-agency",declared["asset_id"])
    assert [item["action"] for item in history]==["declared","stored_unscanned"]
    with pytest.raises(ValueError,match="already been stored"):
        assets.storage_declaration("physical-agency",declared["asset_id"])
    with pytest.raises(ValueError,match="not found"):
        assets.storage_declaration("physical-brand",declared["asset_id"])
    store.close()


def test_storage_lifecycle_rejects_declared_hash_mismatch(tmp_path):
    store=SQLiteStore(tmp_path/"asset-storage-hash.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    declared=declare(assets)
    with pytest.raises(ValueError,match="does not match"):
        assets.record_storage(
            "physical-agency",declared["asset_id"],
            storage_key="b"*64+"/"+declared["asset_id"]+".blob",
            checksum_sha256="f"*64,byte_size=declared["byte_size"],audit=audit(),
        )
    store.close()


def scan_audit():
    return AuditRecord(id=uuid4(),occurred_at=datetime.now(timezone.utc),
        actor_type="system",actor_id="clamav-unix-socket",action="business.asset_scanned",
        subject_type="business_asset",subject_id="test",outcome="scan_clean",
        correlation_id=str(uuid4()),details={})


def _store_declared_asset(assets):
    declared = declare(assets)
    assets.record_storage(
        "physical-agency", declared["asset_id"],
        storage_key="a"*64+"/"+declared["asset_id"]+".blob",
        checksum_sha256=declared["checksum_sha256"], byte_size=declared["byte_size"],
        audit=audit(),
    )
    return declared


def test_asset_scan_verdict_is_scoped_append_only_and_never_downloadable(tmp_path):
    import sqlite3
    store=SQLiteStore(tmp_path/"asset-scan-clean.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    declared=_store_declared_asset(assets)
    scan_target=assets.scan_declaration("physical-agency",declared["asset_id"])
    assert scan_target["storage_key"].endswith(declared["asset_id"]+".blob")
    result=assets.record_scan_result(
        "physical-agency",declared["asset_id"],scanner_key="clamav-unix-socket",
        status="clean",checksum_sha256=declared["checksum_sha256"],
        byte_size=declared["byte_size"],verdict="stream: OK",audit=scan_audit(),
    )
    assert result["status"]=="pending_delivery_approval"
    assert result["download_enabled"] is False
    listed=assets.list("physical-agency")[0]
    assert listed["storage_state"]=="private_scanned_clean"
    assert listed["status"]=="pending_delivery_approval"
    with pytest.raises(ValueError,match="not found"):
        assets.scan_declaration("physical-brand",declared["asset_id"])
    history=assets.events("physical-agency",declared["asset_id"])
    assert [event["action"] for event in history]==["declared","stored_unscanned","scan_clean"]
    with store._lock:
        with pytest.raises(sqlite3.IntegrityError,match="append-only"):
            store._connection.execute("DELETE FROM opencompany_business_asset_scan_events")
    store.close()


def test_infected_asset_scan_is_quarantined_and_hash_mismatch_rejected(tmp_path):
    store=SQLiteStore(tmp_path/"asset-scan-infected.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    declared=_store_declared_asset(assets)
    with pytest.raises(ValueError,match="do not match"):
        assets.record_scan_result(
            "physical-agency",declared["asset_id"],scanner_key="clamav-unix-socket",
            status="clean",checksum_sha256="f"*64,byte_size=declared["byte_size"],
            verdict="stream: OK",audit=scan_audit(),
        )
    result=assets.record_scan_result(
        "physical-agency",declared["asset_id"],scanner_key="clamav-unix-socket",
        status="infected",checksum_sha256=declared["checksum_sha256"],
        byte_size=declared["byte_size"],verdict="stream: Eicar-Test-Signature FOUND",
        audit=scan_audit(),
    )
    assert result["storage_state"]=="quarantined"
    assert result["status"]=="quarantined"
    assert result["download_enabled"] is False
    assert assets.list("physical-agency")[0]["status"]=="quarantined"
    store.close()


def test_asset_registry_rejects_unregistered_or_inactive_business_units(tmp_path):
    store=SQLiteStore(tmp_path/"asset-business-unit-validation.sqlite3")
    units=BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    with pytest.raises(ValueError,match="not found or inactive"):
        declare(assets,business_id="made-up-business")
    with store._lock:
        store._connection.execute(
            "UPDATE opencompany_business_units SET status='inactive' WHERE business_id='physical-brand'"
        )
        store._connection.commit()
    with pytest.raises(ValueError,match="not found or inactive"):
        declare(assets,business_id="physical-brand")
    with pytest.raises(ValueError,match="not found or inactive"):
        assets.list("physical-brand")
    assert units.require_active("physical-agency")["status"] == "active"
    store.close()


def test_asset_declaration_and_audit_event_roll_back_together(tmp_path):
    store=SQLiteStore(tmp_path/"asset-atomicity.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    with store._lock:
        store._connection.execute("""CREATE TRIGGER reject_asset_event BEFORE INSERT ON opencompany_business_asset_events
            BEGIN SELECT RAISE(ABORT,'simulated audit sink failure'); END""")
        store._connection.commit()
    with pytest.raises(Exception,match="simulated audit sink failure"):
        declare(assets,asset_key="atomicity-check")
    assert assets.list("physical-agency") == ()
    with store._lock:
        store._connection.execute("DROP TRIGGER reject_asset_event")
        store._connection.commit()
    store.close()


def test_storage_key_must_match_the_exact_business_asset_scope(tmp_path):
    store=SQLiteStore(tmp_path/"asset-exact-scope.sqlite3")
    BusinessUnitRegistry(store._connection,store._lock)
    assets=BusinessAssetRegistry(store._connection,store._lock)
    declared=declare(assets)
    wrong_scope="f"*64+"/"+declared["asset_id"]+".blob"
    with pytest.raises(ValueError,match="private scope"):
        assets.record_storage(
            "physical-agency",declared["asset_id"],storage_key=wrong_scope,
            checksum_sha256=declared["checksum_sha256"],byte_size=declared["byte_size"],audit=audit(),
        )
    result=assets.record_storage(
        "physical-agency",declared["asset_id"],storage_key=expected_storage_key("physical-agency",declared),
        checksum_sha256=declared["checksum_sha256"],byte_size=declared["byte_size"],audit=audit(),
    )
    assert result["storage_key"]==expected_storage_key("physical-agency",declared)
    store.close()
