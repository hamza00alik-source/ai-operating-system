from __future__ import annotations

import asyncio
import hashlib
from uuid import uuid4

import pytest

from opencompany_core.asset_storage import AssetStorageError, PrivateFilesystemAssetStorage


def test_private_storage_verifies_actual_bytes_and_writes_private_file(tmp_path):
    root = tmp_path / "private-assets"
    payload = b"OpenCompany private asset bytes"
    storage = PrivateFilesystemAssetStorage(root)
    asset_id = str(uuid4())
    result = storage.store(
        business_id="physical-agency",
        asset_scope_id="scope-agency",
        asset_id=asset_id,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_size=len(payload),
        chunks=[payload[:8], payload[8:]],
    )
    stored = root / result["storage_key"]
    assert stored.read_bytes() == payload
    assert stored.stat().st_mode & 0o777 == 0o600
    assert root.stat().st_mode & 0o777 == 0o700
    assert result["checksum_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["byte_size"] == len(payload)


def test_private_storage_rejects_checksum_and_size_mismatch_without_residue(tmp_path):
    root = tmp_path / "private-assets"
    storage = PrivateFilesystemAssetStorage(root)
    payload = b"actual bytes"
    with pytest.raises(AssetStorageError, match="checksum"):
        storage.store(
            business_id="physical-agency", asset_scope_id="scope-a",
            asset_id=str(uuid4()), expected_sha256="0" * 64,
            expected_size=len(payload), chunks=[payload],
        )
    with pytest.raises(AssetStorageError, match="size"):
        storage.store(
            business_id="physical-agency", asset_scope_id="scope-a",
            asset_id=str(uuid4()), expected_sha256=hashlib.sha256(payload).hexdigest(),
            expected_size=len(payload) + 1, chunks=[payload],
        )
    assert not list(root.rglob("*.blob"))
    assert not list(root.rglob("*.part"))


def test_private_storage_separates_business_scopes_and_prevents_overwrite(tmp_path):
    storage = PrivateFilesystemAssetStorage(tmp_path / "private-assets")
    payload = b"same content"
    digest = hashlib.sha256(payload).hexdigest()
    asset_id = str(uuid4())
    first = storage.store(
        business_id="physical-agency", asset_scope_id="agency-scope",
        asset_id=asset_id, expected_sha256=digest, expected_size=len(payload), chunks=[payload],
    )
    second = storage.store(
        business_id="physical-brand", asset_scope_id="brand-scope",
        asset_id=asset_id, expected_sha256=digest, expected_size=len(payload), chunks=[payload],
    )
    assert first["storage_key"] != second["storage_key"]
    with pytest.raises(AssetStorageError, match="already exist"):
        storage.store(
            business_id="physical-agency", asset_scope_id="agency-scope",
            asset_id=asset_id, expected_sha256=digest, expected_size=len(payload), chunks=[payload],
        )


def test_private_storage_rejects_symlinked_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(AssetStorageError, match="symlink"):
        PrivateFilesystemAssetStorage(link)


def test_private_storage_accepts_async_bounded_stream(tmp_path):
    storage = PrivateFilesystemAssetStorage(tmp_path / "private-assets")
    payload = b"streamed private asset"
    async def chunks():
        yield payload[:7]
        yield payload[7:]
    result = asyncio.run(storage.store_stream(
        business_id="digital-products", asset_scope_id="digital-scope",
        asset_id=str(uuid4()), expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_size=len(payload), chunks=chunks(),
    ))
    assert result["checksum_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["byte_size"] == len(payload)
    assert not list((tmp_path / "private-assets").glob(".incoming-*.part"))
