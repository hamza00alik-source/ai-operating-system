"""Private, local asset-byte storage primitives for OpenCompany.

This adapter is intentionally not wired to an HTTP upload or download route yet.
It accepts only server-supplied business scope identity and verifies actual
bytes before atomically placing them in a private directory. It never serves
files and never claims malware scanning or durable-host verification.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Iterable
from uuid import UUID


MAX_ASSET_BYTES = 104_857_600
_BUSINESS_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class AssetStorageError(ValueError):
    """A private asset could not be safely stored."""


_MEDIA_SIGNATURES = {
    "model/gltf-binary": lambda data: len(data) >= 12 and data[:4] == b"glTF" and data[4:8] == b"\x02\x00\x00\x00",
    "image/png": lambda data: data.startswith(b"\x89PNG\\r\\n\x1a\\n"),
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
    "image/webp": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    "application/pdf": lambda data: data.startswith(b"%PDF-"),
    "application/zip": lambda data: data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
    "text/plain": lambda data: b"\x00" not in data and _is_utf8_text(data),
}


def _is_utf8_text(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def validate_asset_media_type(media_type: str, prefix: bytes) -> None:
    """Sniff supported file signatures instead of trusting Content-Type headers."""
    checker = _MEDIA_SIGNATURES.get(media_type)
    if checker is None:
        raise AssetStorageError("unsupported media type for private asset upload")
    if not checker(prefix):
        raise AssetStorageError("uploaded bytes do not match the declared media type")


class PrivateFilesystemAssetStorage:
    """Write-once private filesystem storage with byte-level integrity checks.

    Configure an explicit absolute root (normally a directory on the Railway
    persistent volume, e.g. /data/opencompany-assets). The caller must derive
    business_id and asset_scope_id from the trusted business-unit registry.
    """

    def __init__(self, root: str | Path):
        candidate = Path(root).expanduser()
        if not candidate.is_absolute() or ".." in candidate.parts:
            raise AssetStorageError("asset storage root must be absolute and must not contain parent traversal")
        self.root = candidate
        self._prepare_private_directory(self.root)

    @staticmethod
    def _prepare_private_directory(path: Path) -> None:
        """Create each component without following symlinks; restrict the leaf."""
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                try:
                    current.mkdir(mode=0o700)
                except FileExistsError:
                    pass
                info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise AssetStorageError("asset storage path contains a symlink or non-directory component")
        try:
            os.chmod(path, 0o700, follow_symlinks=False)
        except (NotImplementedError, OSError) as exc:
            raise AssetStorageError("could not enforce private directory permissions") from exc
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise AssetStorageError("asset storage root is not a private directory")

    @staticmethod
    def _scope_directory(business_id: str, asset_scope_id: str) -> str:
        if not isinstance(business_id, str) or not _BUSINESS_ID.fullmatch(business_id):
            raise AssetStorageError("invalid business identity")
        if not isinstance(asset_scope_id, str) or not asset_scope_id.strip() or len(asset_scope_id) > 200:
            raise AssetStorageError("invalid asset scope identity")
        return hashlib.sha256((business_id + "\0" + asset_scope_id).encode("utf-8")).hexdigest()

    def store(
        self,
        *,
        business_id: str,
        asset_scope_id: str,
        asset_id: str,
        expected_sha256: str,
        expected_size: int,
        chunks: Iterable[bytes],
    ) -> dict[str, str | int]:
        """Verify the received stream and atomically store it without overwrite."""
        try:
            canonical_asset_id = str(UUID(asset_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AssetStorageError("asset_id must be a UUID") from exc
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise AssetStorageError("expected_sha256 must be lowercase SHA-256 hex")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or not 0 <= expected_size <= MAX_ASSET_BYTES:
            raise AssetStorageError("expected_size is outside the supported limit")

        scope_dir_name = self._scope_directory(business_id, asset_scope_id)
        scope_dir = self.root / scope_dir_name
        try:
            scope_dir.mkdir(mode=0o700)
        except FileExistsError:
            info = scope_dir.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise AssetStorageError("business asset directory is not a real directory")
        os.chmod(scope_dir, 0o700, follow_symlinks=False)

        final_path = scope_dir / (canonical_asset_id + ".blob")
        if final_path.exists() or final_path.is_symlink():
            raise AssetStorageError("asset bytes already exist; overwriting is prohibited")

        fd, temp_name = tempfile.mkstemp(prefix=".upload-", suffix=".part", dir=scope_dir)
        temp_path = Path(temp_name)
        digest = hashlib.sha256()
        total = 0
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                for chunk in chunks:
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise AssetStorageError("asset stream must contain bytes")
                    data = bytes(chunk)
                    total += len(data)
                    if total > MAX_ASSET_BYTES or total > expected_size:
                        raise AssetStorageError("received asset exceeds its declared size or the 100 MiB limit")
                    digest.update(data)
                    stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            actual_hash = digest.hexdigest()
            if total != expected_size:
                raise AssetStorageError("received asset size does not match its declaration")
            if actual_hash != expected_sha256:
                raise AssetStorageError("received asset checksum does not match its declaration")
            # Hard-link publication is atomic and fails if the destination exists.
            os.link(temp_path, final_path, follow_symlinks=False)
            temp_path.unlink()
            dir_fd = os.open(scope_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        relative_key = scope_dir_name + "/" + canonical_asset_id + ".blob"
        return {
            "storage_key": relative_key,
            "checksum_sha256": actual_hash,
            "byte_size": total,
        }


    def read_chunks(
        self, *, business_id: str, asset_scope_id: str, asset_id: str, chunk_size: int = 1024 * 1024
    ):
        """Read a private stored object internally; this is not a download interface."""
        try:
            canonical_asset_id = str(UUID(asset_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AssetStorageError("asset_id must be a UUID") from exc
        if not 1 <= chunk_size <= 4 * 1024 * 1024:
            raise AssetStorageError("invalid internal scan chunk size")
        scope_dir = self.root / self._scope_directory(business_id, asset_scope_id)
        target = scope_dir / (canonical_asset_id + ".blob")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags)
        except OSError as exc:
            raise AssetStorageError("private asset bytes are unavailable for scanning") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise AssetStorageError("private asset is not a regular file")
            with os.fdopen(fd, "rb") as stream:
                fd = -1
                while True:
                    block = stream.read(chunk_size)
                    if not block:
                        break
                    yield block
        finally:
            if fd >= 0:
                os.close(fd)

    def discard_uncommitted(
        self, *, business_id: str, asset_scope_id: str, asset_id: str, storage_key: str
    ) -> None:
        """Compensate a failed DB lifecycle commit; never expose this as a user action."""
        try:
            canonical_asset_id = str(UUID(asset_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AssetStorageError("asset_id must be a UUID") from exc
        scope_dir_name = self._scope_directory(business_id, asset_scope_id)
        expected_key = scope_dir_name + "/" + canonical_asset_id + ".blob"
        if storage_key != expected_key:
            raise AssetStorageError("storage key does not match the declared business asset")
        scope_dir = self.root / scope_dir_name
        target = scope_dir / (canonical_asset_id + ".blob")
        info = target.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AssetStorageError("stored asset is not a regular private file")
        target.unlink()
        dir_fd = os.open(scope_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    async def store_stream(
        self,
        *,
        business_id: str,
        asset_scope_id: str,
        asset_id: str,
        expected_sha256: str,
        expected_size: int,
        expected_media_type: str,
        chunks,
    ) -> dict[str, str | int]:
        """Bounded async request streaming without buffering the whole upload in RAM."""
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or not 0 <= expected_size <= MAX_ASSET_BYTES:
            raise AssetStorageError("expected_size is outside the supported limit")
        fd, staging_name = tempfile.mkstemp(prefix=".incoming-", suffix=".part", dir=self.root)
        staging_path = Path(staging_name)
        total = 0
        prefix = bytearray()
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                async for chunk in chunks:
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise AssetStorageError("asset stream must contain bytes")
                    data = bytes(chunk)
                    total += len(data)
                    if total > MAX_ASSET_BYTES or total > expected_size:
                        raise AssetStorageError("received asset exceeds its declared size or the 100 MiB limit")
                    if len(prefix) < 4096:
                        prefix.extend(data[:4096 - len(prefix)])
                    stream.write(data)
                validate_asset_media_type(expected_media_type, bytes(prefix))
                stream.flush()
                os.fsync(stream.fileno())
            if total != expected_size:
                raise AssetStorageError("received asset size does not match its declaration")

            def staged_chunks():
                with staging_path.open("rb") as source:
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        yield block

            return self.store(
                business_id=business_id,
                asset_scope_id=asset_scope_id,
                asset_id=asset_id,
                expected_sha256=expected_sha256,
                expected_size=expected_size,
                chunks=staged_chunks(),
            )
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            staging_path.unlink(missing_ok=True)
