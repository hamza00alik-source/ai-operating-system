from __future__ import annotations

import socket
import struct
import threading

import pytest

from opencompany_core.asset_scanning import AssetScanError, ClamAVUnixSocketScanner


def _fake_clamd(socket_path, verdict):
    received = bytearray()
    ready = threading.Event()

    def read_exact(conn, count):
        data = bytearray()
        while len(data) < count:
            block = conn.recv(count - len(data))
            if not block:
                raise AssertionError("client closed before completing INSTREAM")
            data.extend(block)
        return bytes(data)

    def serve():
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        socket_path.chmod(0o600)
        server.listen(1)
        ready.set()
        try:
            conn, _ = server.accept()
            with conn:
                command = bytearray()
                while not command.endswith(b"\\0"):
                    command.extend(conn.recv(1))
                assert bytes(command) == b"zINSTREAM\\0"
                while True:
                    size = struct.unpack("!I", read_exact(conn, 4))[0]
                    if size == 0:
                        break
                    received.extend(read_exact(conn, size))
                conn.sendall(verdict + b"\\0")
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(2)
    return thread, received


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [(b"stream: OK", "clean"), (b"stream: Eicar-Test-Signature FOUND", "infected")],
)
def test_clamav_scanner_streams_full_bytes_and_requires_definitive_verdict(tmp_path, verdict, expected):
    socket_path = tmp_path / "clamd.sock"
    thread, received = _fake_clamd(socket_path, verdict)
    payload = b"private asset content"
    scanner = ClamAVUnixSocketScanner(socket_path, timeout_seconds=5)
    result = scanner.scan([payload[:5], payload[5:]])
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert bytes(received) == payload
    assert result["status"] == expected
    assert result["byte_size"] == len(payload)
    assert result["verdict"] == verdict.decode()


def test_clamav_scanner_fails_closed_when_socket_is_missing(tmp_path):
    scanner = ClamAVUnixSocketScanner(tmp_path / "missing.sock", timeout_seconds=5)
    with pytest.raises(AssetScanError) as error:
        scanner.scan([b"asset"])
    assert error.value.code == "scanner_unavailable"


def test_clamav_scanner_rejects_regular_file_as_socket(tmp_path):
    path = tmp_path / "not-a-socket"
    path.write_text("not a socket")
    scanner = ClamAVUnixSocketScanner(path, timeout_seconds=5)
    with pytest.raises(AssetScanError) as error:
        scanner.scan([b"asset"])
    assert error.value.code == "invalid_socket"
