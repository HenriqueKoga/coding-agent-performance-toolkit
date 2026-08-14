import json
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from coding_agent_performance.trace.collector import (
    LOOPBACK_HOST,
    MAX_BODY_BYTES,
    CollectorBindError,
    OtlpHttpCollector,
)
from coding_agent_performance.trace.storage import CaptureStorageError, CaptureWriter, make_envelope

SYNTHETIC_LOGS = {
    "resourceLogs": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "synthetic"}}]}}]
}
SYNTHETIC_METRICS = {
    "resourceMetrics": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "synthetic"}}]}}]
}


@pytest.fixture
def collector(tmp_path: Path) -> Iterator[OtlpHttpCollector]:
    writer = CaptureWriter.create(tmp_path / "capture.jsonl")
    instance = OtlpHttpCollector(host=LOOPBACK_HOST, port=0, writer=writer, source="claude-code")
    instance.start()
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.stop()
        thread.join(timeout=2)
        instance.close()


def _post(
    url: str,
    payload: object,
    *,
    content_type: str | None = "application/json",
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    import urllib.error
    import urllib.request

    body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
    request = urllib.request.Request(url, data=body, method="POST")
    if content_type is not None:
        request.add_header("Content-Type", content_type)
    if extra_headers:
        for name, value in extra_headers.items():
            request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _raw(host: str, port: int, request: bytes) -> bytes:
    with socket.create_connection((host, port), timeout=2) as sock:
        sock.sendall(request)
        sock.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)


def _status_line(response: bytes) -> str:
    return response.split(b"\r\n", 1)[0].decode("ascii")


def test_post_logs_persists_and_returns_success(collector: OtlpHttpCollector) -> None:
    status, body = _post(collector.logs_url, SYNTHETIC_LOGS)

    assert status == 200
    assert body == b"{}"
    assert b"resourceLogs" not in body
    lines = collector.writer.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["signal"] == "logs"
    assert row["payload"] == SYNTHETIC_LOGS
    assert collector.stats.log_batches == 1
    assert collector.stats.metric_batches == 0


def test_post_metrics_persists_and_returns_success(collector: OtlpHttpCollector) -> None:
    status, body = _post(collector.metrics_url, SYNTHETIC_METRICS)

    assert status == 200
    assert body == b"{}"
    assert b"resourceMetrics" not in body
    row = json.loads(collector.writer.path.read_text(encoding="utf-8").splitlines()[0])
    assert row["signal"] == "metrics"
    assert row["payload"] == SYNTHETIC_METRICS
    assert collector.stats.metric_batches == 1


def test_unknown_endpoint_returns_404(collector: OtlpHttpCollector) -> None:
    status, body = _post(f"http://{collector.host}:{collector.port}/v1/traces", SYNTHETIC_LOGS)

    assert status == 404
    assert json.loads(body)["message"] == "not found"
    assert collector.writer.path.read_text(encoding="utf-8") == ""
    assert collector.stats.log_batches == 0


def test_get_returns_404(collector: OtlpHttpCollector) -> None:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(collector.logs_url, method="GET")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(request, timeout=2)
    assert exc_info.value.code == 404


def test_invalid_content_length_returns_400(collector: OtlpHttpCollector) -> None:
    request = (
        f"POST /v1/logs HTTP/1.1\r\n"
        f"Host: {collector.host}:{collector.port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: nope\r\n"
        f"\r\n"
    ).encode("ascii")
    response = _raw(collector.host, collector.port, request)

    assert "400" in _status_line(response)
    assert collector.writer.path.read_text(encoding="utf-8") == ""


def test_invalid_json_returns_400(collector: OtlpHttpCollector) -> None:
    status, body = _post(collector.logs_url, b"{not-json", content_type="application/json")

    assert status == 400
    assert json.loads(body)["message"] == "invalid JSON"
    assert collector.writer.path.read_text(encoding="utf-8") == ""
    assert collector.stats.log_batches == 0


@pytest.mark.parametrize("payload", [[], "text", 1, None])
def test_non_object_json_returns_400(collector: OtlpHttpCollector, payload: object) -> None:
    status, _body = _post(collector.logs_url, payload)

    assert status == 400
    assert collector.writer.path.read_text(encoding="utf-8") == ""
    assert collector.stats.log_batches == 0


def test_invalid_content_type_returns_415(collector: OtlpHttpCollector) -> None:
    status, _body = _post(collector.logs_url, SYNTHETIC_LOGS, content_type="text/plain")

    assert status == 415
    assert collector.writer.path.read_text(encoding="utf-8") == ""


def test_json_content_type_with_charset_is_accepted(collector: OtlpHttpCollector) -> None:
    status, body = _post(collector.logs_url, SYNTHETIC_LOGS, content_type="application/json; charset=utf-8")

    assert status == 200
    assert body == b"{}"
    assert collector.stats.log_batches == 1


def test_unsupported_content_encoding_returns_415(collector: OtlpHttpCollector) -> None:
    status, _body = _post(
        collector.logs_url,
        SYNTHETIC_LOGS,
        extra_headers={"Content-Encoding": "gzip"},
    )

    assert status == 415
    assert collector.writer.path.read_text(encoding="utf-8") == ""


def test_payload_over_limit_returns_413(collector: OtlpHttpCollector) -> None:
    request = (
        f"POST /v1/logs HTTP/1.1\r\n"
        f"Host: {collector.host}:{collector.port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {MAX_BODY_BYTES + 1}\r\n"
        f"\r\n"
    ).encode("ascii")
    response = _raw(collector.host, collector.port, request)

    assert "413" in _status_line(response)
    assert collector.writer.path.read_text(encoding="utf-8") == ""
    assert collector.stats.log_batches == 0


def test_missing_content_length_returns_411(collector: OtlpHttpCollector) -> None:
    request = (
        f"POST /v1/logs HTTP/1.1\r\n"
        f"Host: {collector.host}:{collector.port}\r\n"
        f"Content-Type: application/json\r\n"
        f"\r\n"
        f"{{}}"
    ).encode("ascii")
    response = _raw(collector.host, collector.port, request)

    assert "411" in _status_line(response)
    assert collector.writer.path.read_text(encoding="utf-8") == ""


def test_chunked_transfer_encoding_is_rejected(collector: OtlpHttpCollector) -> None:
    request = (
        f"POST /v1/logs HTTP/1.1\r\n"
        f"Host: {collector.host}:{collector.port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Transfer-Encoding: chunked\r\n"
        f"\r\n"
        f"2\r\n{{}}\r\n0\r\n\r\n"
    ).encode("ascii")
    response = _raw(collector.host, collector.port, request)

    assert "400" in _status_line(response)
    assert collector.writer.path.read_text(encoding="utf-8") == ""


def test_rejected_payload_is_not_persisted(collector: OtlpHttpCollector) -> None:
    _post(collector.logs_url, ["nope"])
    _post(collector.metrics_url, SYNTHETIC_METRICS)

    lines = collector.writer.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["signal"] == "metrics"
    assert collector.stats.log_batches == 0
    assert collector.stats.metric_batches == 1


def test_persist_failure_returns_500_without_counting(
    collector: OtlpHttpCollector, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_append(_envelope: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(collector.writer, "append", fail_append)
    status, body = _post(collector.logs_url, SYNTHETIC_LOGS)

    assert status == 500
    assert json.loads(body)["message"] == "failed to persist capture"
    assert collector.stats.log_batches == 0


def test_listens_only_on_loopback(collector: OtlpHttpCollector) -> None:
    assert collector.host == LOOPBACK_HOST
    assert collector.logs_url.startswith("http://127.0.0.1:")
    assert collector.metrics_url.startswith("http://127.0.0.1:")


def test_shutdown_closes_server_and_writer(tmp_path: Path) -> None:
    writer = CaptureWriter.create(tmp_path / "capture.jsonl")
    instance = OtlpHttpCollector(host=LOOPBACK_HOST, port=0, writer=writer, source="claude-code")
    instance.start()
    port = instance.port
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    instance.stop()
    thread.join(timeout=2)
    instance.close()

    with pytest.raises(OSError):
        socket.create_connection((LOOPBACK_HOST, port), timeout=0.5)

    with pytest.raises(CaptureStorageError, match="closed"):
        writer.append(make_envelope(source="claude-code", signal="logs", payload={"resourceLogs": []}))


def test_bind_error_when_port_in_use(tmp_path: Path) -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind((LOOPBACK_HOST, 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    writer = CaptureWriter.create(tmp_path / "capture.jsonl")
    instance = OtlpHttpCollector(host=LOOPBACK_HOST, port=port, writer=writer, source="claude-code")
    try:
        with pytest.raises(CollectorBindError, match="already in use"):
            instance.start()
    finally:
        writer.close()
        occupied.close()


def test_rejects_non_loopback_host(tmp_path: Path) -> None:
    writer = CaptureWriter.create(tmp_path / "capture.jsonl")
    try:
        with pytest.raises(CollectorBindError, match=r"127\.0\.0\.1"):
            OtlpHttpCollector(host="0.0.0.0", port=4318, writer=writer, source="claude-code")
    finally:
        writer.close()
