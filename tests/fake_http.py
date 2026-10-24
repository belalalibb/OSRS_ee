"""A scripted local HTTP server (127.0.0.1 only) for S06b/S07b-local tests.

Each incoming request is recorded (path, headers, JSON body); the response is the
next scripted (status, body) item, or the default. No external network.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Optional

from tests.conftest import loopback_only


class FakeHttpServer:
    def __init__(self, default: tuple[int, Any] = (200, {"ok": True, "result": {}})) -> None:
        self.default = default
        self.script: Deque[tuple[int, Any]] = deque()
        self.requests: list[dict] = []
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.delay_seconds = 0.0

    def plan(self, *items: tuple[int, Any]) -> "FakeHttpServer":
        self.script.extend(items)
        return self

    @property
    def base_url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "FakeHttpServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):  # silence
                pass

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else None
                except ValueError:
                    body = raw
                with outer._lock:
                    outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                    status, payload = outer.script.popleft() if outer.script else outer.default
                if outer.delay_seconds:
                    import time
                    time.sleep(outer.delay_seconds)
                data = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST  # noqa: N815

        self._cm = loopback_only()
        self._cm.__enter__()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()
        self._cm.__exit__(None, None, None)
