"""Harness guard for S01: any socket use is a failure (no game/AI/Telegram network).

Exception (S06b/S07b-local): tests that exercise the real HTTP transports against a
fake server on 127.0.0.1 use ``loopback_only()`` which temporarily restores the real
socket class but refuses any connect() to a non-loopback address.
"""
import contextlib
import socket

_REAL_SOCKET = socket.socket
_REAL_CREATE_CONNECTION = socket.create_connection


def _forbidden(*_a, **_k):
    raise RuntimeError("network forbidden in S01 tests")


socket.socket = _forbidden  # type: ignore[assignment]
socket.create_connection = _forbidden  # type: ignore[assignment]

_LOOPBACK = ("127.0.0.1", "localhost", "::1")


class _LoopbackSocket(_REAL_SOCKET):  # type: ignore[misc,valid-type]
    def connect(self, address):  # type: ignore[override]
        if isinstance(address, tuple) and address and address[0] not in _LOOPBACK:
            raise RuntimeError(f"non-loopback connect refused in tests: {address[0]}")
        return super().connect(address)

    def connect_ex(self, address):  # type: ignore[override]
        if isinstance(address, tuple) and address and address[0] not in _LOOPBACK:
            raise RuntimeError(f"non-loopback connect refused in tests: {address[0]}")
        return super().connect_ex(address)


def _loopback_create_connection(address, *a, **k):
    if address[0] not in _LOOPBACK:
        raise RuntimeError(f"non-loopback connect refused in tests: {address[0]}")
    return _REAL_CREATE_CONNECTION(address, *a, **k)


@contextlib.contextmanager
def loopback_only():
    """Allow sockets to 127.0.0.1/localhost only, for the duration of the block."""
    socket.socket = _LoopbackSocket  # type: ignore[misc]
    socket.create_connection = _loopback_create_connection  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = _forbidden  # type: ignore[assignment]
        socket.create_connection = _forbidden  # type: ignore[assignment]
