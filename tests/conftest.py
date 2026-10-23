"""Harness guard for S01: any socket use is a failure (no game/AI/Telegram network)."""
import socket

def _forbidden(*_a, **_k):
    raise RuntimeError("network forbidden in S01 tests")

socket.socket = _forbidden  # type: ignore[assignment]
socket.create_connection = _forbidden  # type: ignore[assignment]
