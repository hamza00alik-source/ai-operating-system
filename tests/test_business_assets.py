from datetime import datetime, timezone
from uuid import uuid4
import pytest
from opencompany_core.domain import AuditRecord
from opencompany_core.persistence import SQLiteStore
from opencompany_core.business_units import BusinessUnitRegistry
from opencompany_core.business_assets import BusinessAssetRegistry


def audit(actor_type="owner"):
    return AuditRecord(id=uuid4(),occurred_at=datetime.now(timezone.utc),
        actor_type=actor_type,actor_id="owner",action="business.asset_declared",
        subject_type="business_asset",subject_id="test",outcome="pending_storage",
        correlation_id=str(uuid4()),details={})


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
        storage_key="a"*64+"/"+declared["asset_id"]+".blob",
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
