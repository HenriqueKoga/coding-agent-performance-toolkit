"""Loopback-only OTLP HTTP/JSON receiver.

This is a local ingestion boundary for CAPT. It is not a generic
OpenTelemetry Collector and must not be exposed on a network.
"""

import errno
import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final

from coding_agent_performance.trace.storage import CaptureStorageError, CaptureWriter, make_envelope

LOOPBACK_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 4318
MAX_BODY_BYTES: Final = 8 * 1024 * 1024
_JSON_CONTENT_TYPE: Final = "application/json"
_SUCCESS_BODY: Final = b"{}"
_ROUTES: Final = {
    "/v1/logs": "logs",
    "/v1/metrics": "metrics",
}


class CollectorBindError(Exception):
    """Expected failure while binding the loopback receiver."""


@dataclass(frozen=True, slots=True)
class CollectorStats:
    log_batches: int
    metric_batches: int


class _Stats:
    def __init__(self) -> None:
        self.log_batches = 0
        self.metric_batches = 0

    def increment(self, signal: str) -> None:
        if signal == "logs":
            self.log_batches += 1
        elif signal == "metrics":
            self.metric_batches += 1

    def snapshot(self) -> CollectorStats:
        return CollectorStats(log_batches=self.log_batches, metric_batches=self.metric_batches)


class _CollectorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], writer: CaptureWriter, source: str, max_body_bytes: int) -> None:
        self.writer = writer
        self.source = source
        self.max_body_bytes = max_body_bytes
        self.stats = _Stats()
        super().__init__(address, _CollectorHandler)

    def handle_error(self, request: object, client_address: object) -> None:
        return


class _CollectorHandler(BaseHTTPRequestHandler):
    server: _CollectorServer
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        signal = _ROUTES.get(self.path.split("?", 1)[0])
        if signal is None:
            self._send_status(404, "not found")
            return
        try:
            payload = self._read_json_object()
        except _HttpFailure as exc:
            self._send_status(exc.status, exc.message)
            return
        envelope = make_envelope(source=self.server.source, signal=signal, payload=payload)
        try:
            self.server.writer.append(envelope)
        except CaptureStorageError, OSError:
            self._send_status(500, "failed to persist capture")
            return
        self.server.stats.increment(signal)
        self._send_bytes(200, _SUCCESS_BODY)

    def do_GET(self) -> None:
        self._send_status(404, "not found")

    def do_HEAD(self) -> None:
        self._send_status(404, "not found")

    def do_PUT(self) -> None:
        self._send_status(404, "not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def log_error(self, format: str, *args: object) -> None:
        return

    def _read_json_object(self) -> dict[str, object]:
        transfer_encoding = self.headers.get("Transfer-Encoding")
        if transfer_encoding is not None and transfer_encoding.strip().lower() not in {"", "identity"}:
            raise _HttpFailure(400, "chunked transfer encoding is not supported")
        content_encoding = self.headers.get("Content-Encoding")
        if content_encoding is not None and content_encoding.strip().lower() not in {"", "identity"}:
            raise _HttpFailure(415, "unsupported content encoding")
        if not _is_json_content_type(self.headers.get("Content-Type")):
            raise _HttpFailure(415, "unsupported content type")
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            raise _HttpFailure(411, "content length is required")
        try:
            length = int(length_header)
        except ValueError:
            raise _HttpFailure(400, "invalid content length") from None
        if length < 0:
            raise _HttpFailure(400, "invalid content length")
        if length > self.server.max_body_bytes:
            raise _HttpFailure(413, "payload too large")
        body = self.rfile.read(length)
        if len(body) != length:
            raise _HttpFailure(400, "incomplete request body")
        try:
            decoded = body.decode("utf-8")
            parsed: object = json.loads(decoded)
        except UnicodeDecodeError, json.JSONDecodeError:
            raise _HttpFailure(400, "invalid JSON") from None
        if not isinstance(parsed, dict):
            raise _HttpFailure(400, "JSON payload must be an object")
        return parsed

    def _send_status(self, status: int, message: str) -> None:
        body = json.dumps({"message": message}, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, body)

    def _send_bytes(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", _JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


class _HttpFailure(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _is_json_content_type(value: str | None) -> bool:
    if value is None:
        return False
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == _JSON_CONTENT_TYPE


class OtlpHttpCollector:
    def __init__(
        self,
        *,
        host: str = LOOPBACK_HOST,
        port: int = DEFAULT_PORT,
        writer: CaptureWriter,
        source: str,
        max_body_bytes: int = MAX_BODY_BYTES,
    ) -> None:
        if host != LOOPBACK_HOST:
            raise CollectorBindError("Collector host must be 127.0.0.1.")
        self.host = host
        self.port = port
        self.writer = writer
        self.source = source
        self.max_body_bytes = max_body_bytes
        self._httpd: _CollectorServer | None = None

    @property
    def logs_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1/logs"

    @property
    def metrics_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1/metrics"

    @property
    def stats(self) -> CollectorStats:
        if self._httpd is None:
            return CollectorStats(log_batches=0, metric_batches=0)
        return self._httpd.stats.snapshot()

    def start(self) -> None:
        try:
            httpd = _CollectorServer((self.host, self.port), self.writer, self.source, self.max_body_bytes)
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                raise CollectorBindError(f"Port {self.port} is already in use on {self.host}.") from exc
            detail = exc.strerror or str(exc)
            raise CollectorBindError(f"Could not bind to {self.host}:{self.port}: {detail}") from exc
        self._httpd = httpd
        self.port = httpd.server_port

    def serve_forever(self) -> None:
        if self._httpd is None:
            raise CollectorBindError("Collector has not been started.")
        self._httpd.serve_forever(poll_interval=0.5)

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()

    def close(self) -> CollectorStats:
        stats = self.stats
        if self._httpd is not None:
            self._httpd.server_close()
            self._httpd = None
        self.writer.close()
        return stats
