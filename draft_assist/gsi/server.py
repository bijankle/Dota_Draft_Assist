"""Local HTTP listener for Dota's Game State Integration POSTs.

Dota pushes JSON to http://127.0.0.1:<port>/ several times a second while it
is running. This server keeps the newest payload, and — crucially for
working out what GSI actually provides — can archive raw payloads to disk so
they can be inspected offline and replayed into tests.

Bound to 127.0.0.1 only: nothing outside this machine can reach it. The auth
token Dota sends is checked, so another local program cannot feed us state.
"""

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 4 * 1024 * 1024      # generous; real payloads are ~10-60 KB


@dataclass
class Reception:
    payload: dict | None = None
    received_at: float = 0.0
    count: int = 0
    rejected: int = 0            # payloads refused for a bad auth token
    last_error: str = ""

    @property
    def age(self) -> float:
        return time.monotonic() - self.received_at if self.received_at else 1e9

    @property
    def live(self) -> bool:
        """Dota's heartbeat is ~10 s, so silence beyond that means the game
        is closed or the launch option is missing."""
        return self.payload is not None and self.age < 15.0


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    """An HTTP server that refuses to share its port.

    http.server sets allow_reuse_address = 1, which on Linux only bypasses
    TIME_WAIT — but on WINDOWS it permits two sockets to bind the same
    address and port, with undefined delivery between them. A second copy of
    this app would then bind 53000 "successfully" and silently receive
    nothing while the first copy got every payload: two windows disagreeing
    about whether Dota is sending anything, which is impossible to diagnose
    from the symptom. Binding exclusively turns that into a loud, obvious
    error instead.
    """

    allow_reuse_address = False

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:          # Windows only
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            except OSError:
                pass                        # best effort; the bind still checks
        super().server_bind()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        server: "GsiServer" = self.server.gsi          # type: ignore[attr-defined]
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_response(400)
            self.end_headers()
            return
        body = self.rfile.read(length)
        # Ingest before replying: parsing is sub-millisecond against Dota's
        # 5 s timeout, and doing it first means a payload is observable the
        # moment the POST returns rather than a scheduling hiccup later.
        server.ingest(body)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        payload = b"Dota Draft Assist GSI listener\n"
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args) -> None:
        """Silence the default stderr access log; a windowless app has no
        console and the state itself is what matters."""


class GsiServer:
    def __init__(self, port: int, token: str | None = None,
                 archive_dir: Path | None = None):
        self.port = port
        self.token = token
        self.archive_dir = archive_dir
        self.reception = Reception()
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._archived = 0

    # -- lifecycle -------------------------------------------------------
    def start(self, attempts: int = 3, delay: float = 0.4) -> None:
        """Bind the listener, retrying briefly.

        Binding exclusively (see _ExclusiveHTTPServer) means a port left over
        from a previous run can still be settling when the app is restarted
        quickly. A short retry absorbs that without weakening the guarantee
        that two copies can never share the port; a genuine clash still
        raises, just over a second later.
        """
        last: OSError | None = None
        httpd = None
        for attempt in range(attempts):
            try:
                httpd = _ExclusiveHTTPServer(("127.0.0.1", self.port),
                                             _Handler)
                break
            except OSError as exc:
                last = exc
                if attempt < attempts - 1:
                    time.sleep(delay)
        if httpd is None:
            raise last if last else OSError("could not bind the GSI port")
        httpd.gsi = self                       # type: ignore[attr-defined]
        httpd.daemon_threads = True
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever,
                                        name="gsi-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    # -- ingestion -------------------------------------------------------
    def ingest(self, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            with self._lock:
                self.reception.last_error = f"unparseable payload: {exc}"
            return
        if not isinstance(payload, dict):
            with self._lock:
                self.reception.last_error = "payload was not a JSON object"
            return
        if self.token:
            sent = (payload.get("auth") or {}).get("token")
            if sent != self.token:
                with self._lock:
                    self.reception.rejected += 1
                    self.reception.last_error = (
                        "auth token mismatch — Dota is using a different "
                        "config; reinstall GSI from the app")
                return
        with self._lock:
            self.reception.payload = payload
            self.reception.received_at = time.monotonic()
            self.reception.count += 1
            self.reception.last_error = ""
        self._archive(payload)

    def _archive(self, payload: dict) -> None:
        if self.archive_dir is None:
            return
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._archived += 1
        path = self.archive_dir / f"gsi_{self._archived:05d}.json"
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass

    def snapshot(self) -> Reception:
        with self._lock:
            return Reception(payload=self.reception.payload,
                             received_at=self.reception.received_at,
                             count=self.reception.count,
                             rejected=self.reception.rejected,
                             last_error=self.reception.last_error)
