from pathlib import Path

import pytest

from coding_agent_performance.adapters.claude_code.telemetry import ClaudeCodeExportConfig


def test_snippet_contains_http_json_endpoints() -> None:
    config = ClaudeCodeExportConfig(
        logs_endpoint="http://127.0.0.1:4318/v1/logs",
        metrics_endpoint="http://127.0.0.1:4318/v1/metrics",
    )
    snippet = config.shell_snippet()

    assert "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json" in snippet
    assert "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/json" in snippet
    assert "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://127.0.0.1:4318/v1/logs" in snippet
    assert "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics" in snippet


def test_snippet_enables_logs_and_metrics() -> None:
    snippet = ClaudeCodeExportConfig(
        logs_endpoint="http://127.0.0.1:4319/v1/logs",
        metrics_endpoint="http://127.0.0.1:4319/v1/metrics",
    ).shell_snippet()

    assert "CLAUDE_CODE_ENABLE_TELEMETRY=1" in snippet
    assert "OTEL_LOGS_EXPORTER=otlp" in snippet
    assert "OTEL_METRICS_EXPORTER=otlp" in snippet
    assert snippet.strip().endswith("claude")


def test_snippet_disables_sensitive_fields() -> None:
    snippet = ClaudeCodeExportConfig(
        logs_endpoint="http://127.0.0.1:4318/v1/logs",
        metrics_endpoint="http://127.0.0.1:4318/v1/metrics",
    ).shell_snippet()

    assert "OTEL_LOG_USER_PROMPTS=0" in snippet
    assert "OTEL_LOG_ASSISTANT_RESPONSES=0" in snippet
    assert "OTEL_LOG_TOOL_DETAILS=0" in snippet
    assert "OTEL_LOG_TOOL_CONTENT=0" in snippet


def test_snippet_has_no_api_key() -> None:
    snippet = ClaudeCodeExportConfig(
        logs_endpoint="http://127.0.0.1:4318/v1/logs",
        metrics_endpoint="http://127.0.0.1:4318/v1/metrics",
    ).shell_snippet()
    lowered = snippet.lower()

    assert "api_key" not in lowered
    assert "api-key" not in lowered
    assert "authorization" not in lowered
    assert "sk-" not in lowered
    assert "anthropic" not in lowered


def test_adapter_does_not_write_user_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = ClaudeCodeExportConfig(
        logs_endpoint="http://127.0.0.1:4318/v1/logs",
        metrics_endpoint="http://127.0.0.1:4318/v1/metrics",
    )
    config.environment()
    config.shell_snippet()

    assert list(tmp_path.iterdir()) == []
