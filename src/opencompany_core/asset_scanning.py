"""Fail-closed local ClamAV scanner adapter.

Only a Unix-domain socket is supported: no remote scanner endpoint or paid API.
A clean verdict means ClamAV accepted the complete stream and returned OK.
An unavailable, malformed, or size-limited scanner response is an error, never
a clean verdict.
"""
from __future__ import annotations

import hashlib
import os
import socket
import stat
import struct
from pathlib import Path
from typing import Iterable


MAX_ASSET_BYTES = 104_857_600


class AssetScanError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ClamAVUnixSocketScanner:
    """Stream asset bytes to a local clamd Unix socket using INSTREAM."""

    scanner_key = "clamav-unix-socket"

    def __init__(self, socket_path: str | Path, *, timeout_seconds: float = 120.0):
        path = Path(socket_path).expanduser()
        if not path.is_absolute() or ".." in path.parts:
            raise AssetScanError("invalid_socket_path", "ClamAV socket path must be absolute and contain no parent traversal")
        if not 1 <= timeout_seconds <= 600:
            raise AssetScanError("invalid_timeout", "ClamAV timeout is outside the supported range")
        self.socket_path = path
        self.timeout_seconds = timeout_seconds

    def _verify_socket(self) -> None:
        try:
            info = self.socket_path.lstat()
        except OSError as exc:
            raise AssetScanError("scanner_unavailable", "Local malware scanner socket is unavailable") from exc
        if not stat.S_ISSOCK(info.st_mode):
            raise AssetScanError("invalid_socket", "Configured ClamAV endpoint is not a Unix socket")
        if info.st_mode & 0o022:
            raise AssetScanError("unsafe_socket_permissions", "ClamAV socket must not be group/world writable")

    def scan(self, chunks: Iterable[bytes]) -> dict[str, str | int]:
        self._verify_socket()
        digest = hashlib.sha256()
        total = 0
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(self.timeout_seconds)
        try:
            client.connect(str(self.socket_path))
            client.sendall(b"zINSTREAM\0")
            for chunk in chunks:
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise AssetScanError("invalid_stream", "Scanner input must contain bytes")
                data = bytes(chunk)
                if not data:
                    continue
                total += len(data)
                if total > MAX_ASSET_BYTES:
                    raise AssetScanError("scan_size_limit", "Asset exceeds the malware scanner size limit")
                digest.update(data)
                client.sendall(struct.pack("!I", len(data)))
                client.sendall(data)
            client.sendall(struct.pack("!I", 0))
            response = bytearray()
            while len(response) < 4096:
                block = client.recv(min(1024, 4096 - len(response)))
                if not block:
                    break
                response.extend(block)
                if b"\0" in response or b"\\n" in response:
                    break
        except socket.timeout as exc:
            raise AssetScanError("scanner_timeout", "Local malware scanner timed out") from exc
        except OSError as exc:
            raise AssetScanError("scanner_io_error", "Local malware scanner could not complete the scan") from exc
        finally:
            client.close()

        verdict = bytes(response).split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()
        if verdict.endswith(": OK") or verdict == "stream: OK":
            status = "clean"
        elif verdict.endswith(" FOUND"):
            status = "infected"
        else:
            raise AssetScanError("scanner_invalid_response", "Local malware scanner did not return a definitive verdict")
        return {
            "status": status,
            "scanner_key": self.scanner_key,
            "checksum_sha256": digest.hexdigest(),
            "byte_size": total,
            "verdict": verdict[:500],
        }
