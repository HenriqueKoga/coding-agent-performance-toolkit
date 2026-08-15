import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coding_agent_performance.trace.capture import CaptureError
from coding_agent_performance.trace.rendering import render_json, render_text
from coding_agent_performance.trace.summary import summarize_capture
from tests.helpers.otlp import envelope, number_point, resource_logs, resource_metrics, sum_metric
from tests.helpers.synthetic_capture import FIXTURE_PATH, write_synthetic_capture


def test_synthetic_fixture_uses_api_request_events() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    usage = summary.model_usage
    assert usage.usage_source == "api_request_events"
    assert usage.requests == 4
    assert usage.errors == 1
    assert usage.estimated_cost_usd_micros == 12345
    assert usage.tokens.input == 1000
    assert usage.tokens.output == 500
    assert usage.tokens.cache_read == 800
    assert usage.tokens.cache_creation == 100
    assert usage.duration_ms.total == 4000
    assert usage.duration_ms.average == 1000.0
    assert usage.duration_ms.p50 == 900
    assert usage.duration_ms.p95 == 1500
    assert [row.model for row in usage.by_model] == ["claude-example", "claude-other"]
    assert [row.query_source for row in usage.by_query_source] == ["main", "subagent"]
    assert summary.sessions.count == 1
    assert summary.sessions.prompts == 2
    assert summary.sessions.assistant_responses == 4
    assert summary.tools.calls == 3
    assert summary.tools.successes == 2
    assert summary.tools.failures == 1
    assert summary.tools.input_bytes == 400
    assert summary.tools.result_bytes == 2000
    assert summary.tools.duration_ms.p50 == 300
    assert summary.tools.duration_ms.p95 == 700
    bash = next(row for row in summary.tools.by_name if row.name == "Bash")
    assert bash.success_rate == 0.5
    assert summary.activity.active_time.user_seconds == 20.0
    assert summary.activity.active_time.cli_seconds == 40.0
    assert summary.coverage.duplicate_log_records == 1
    assert summary.coverage.duplicate_metric_points == 1
    assert summary.coverage.unsupported_metric_points == 1
    assert summary.coverage.unknown_events == (("weird_event", 1),)
    assert dict(summary.coverage.unknown_metrics)["custom.unknown.metric"] == 1
    assert summary.capture.file == "synthetic-capture.jsonl"
    assert "/" not in summary.capture.file


def test_does_not_add_metrics_when_api_requests_exist() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    assert summary.model_usage.tokens.input == 1000
    assert summary.model_usage.estimated_cost_usd_micros == 12345


def test_metrics_fallback_when_no_api_requests(tmp_path: Path) -> None:
    path = tmp_path / "metrics-only.jsonl"
    payload = resource_metrics(
        [
            sum_metric(
                "claude_code.token.usage",
                [
                    number_point(
                        value=10, attributes={"type": "input", "model": "claude-example", "query_source": "main"}
                    ),
                    number_point(
                        value=4, attributes={"type": "output", "model": "claude-example", "query_source": "main"}
                    ),
                    number_point(
                        value=2, attributes={"type": "cacheRead", "model": "claude-example", "query_source": "main"}
                    ),
                    number_point(
                        value=1, attributes={"type": "cacheCreation", "model": "claude-example", "query_source": "main"}
                    ),
                ],
                temporality=1,
            ),
            sum_metric(
                "claude_code.cost.usage",
                [number_point(value=0.000012, attributes={"model": "claude-example", "query_source": "main"})],
                temporality=1,
            ),
        ]
    )
    path.write_text(json.dumps(envelope(signal="metrics", payload=payload)) + "\n", encoding="utf-8")
    summary = summarize_capture(path)
    assert summary.model_usage.usage_source == "otel_metrics"
    assert summary.model_usage.requests == 0
    assert summary.model_usage.tokens.input == 10
    assert summary.model_usage.tokens.output == 4
    assert summary.model_usage.tokens.cache_read == 2
    assert summary.model_usage.tokens.cache_creation == 1
    assert summary.model_usage.estimated_cost_usd_micros == 12
    assert summary.model_usage.by_model[0].model == "claude-example"
    assert summary.model_usage.by_query_source[0].query_source == "main"


def test_empty_recognized_data_fails(tmp_path: Path) -> None:
    path = tmp_path / "empty-data.jsonl"
    path.write_text(json.dumps(envelope(signal="logs", payload=resource_logs([]))) + "\n", encoding="utf-8")
    with pytest.raises(CaptureError, match="no recognized telemetry"):
        summarize_capture(path)


def test_fixture_writer_roundtrip(tmp_path: Path) -> None:
    path = write_synthetic_capture(tmp_path / "copy.jsonl")
    assert summarize_capture(path).model_usage.requests == 4


def test_unknown_any_value_reaches_coverage_without_content(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "resourceLogs": [
            {
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "attributes": [
                                    {"key": "event.name", "value": {"stringValue": "user_prompt"}},
                                    {"key": "prompt_length", "value": {"intValue": 1}},
                                    {"key": "weird", "value": {"mysteryValue": "hidden-secret"}},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    path = tmp_path / "unknown-value.jsonl"
    path.write_text(json.dumps(envelope(signal="logs", payload=payload)) + "\n", encoding="utf-8")
    summary = summarize_capture(path)
    assert summary.coverage.unknown_otlp_values == 1
    assert "hidden-secret" not in render_json(summary)
    assert "hidden-secret" not in render_text(summary)


def test_usage_source_none_for_tools_only(tmp_path: Path) -> None:
    payload = resource_logs(
        [
            {
                "attributes": [
                    {"key": "event.name", "value": {"stringValue": "tool_result"}},
                    {"key": "tool_name", "value": {"stringValue": "Read"}},
                    {"key": "success", "value": {"stringValue": "true"}},
                    {"key": "duration_ms", "value": {"intValue": 10}},
                ]
            }
        ]
    )
    path = tmp_path / "tools-only.jsonl"
    path.write_text(json.dumps(envelope(signal="logs", payload=payload)) + "\n", encoding="utf-8")
    summary = summarize_capture(path)
    assert summary.model_usage.usage_source == "none"
    assert summary.tools.calls == 1


def test_usage_source_none_for_activity_metrics_only(tmp_path: Path) -> None:
    payload = resource_metrics([sum_metric("claude_code.commit.count", [number_point(value=2)], temporality=1)])
    path = tmp_path / "activity-only.jsonl"
    path.write_text(json.dumps(envelope(signal="metrics", payload=payload)) + "\n", encoding="utf-8")
    summary = summarize_capture(path)
    assert summary.model_usage.usage_source == "none"
    assert summary.activity.commits == 2


def test_received_at_is_timezone_aware() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    first = datetime.fromisoformat(summary.capture.first_received_at or "")
    assert first.tzinfo is not None
    assert first.utcoffset() == UTC.utcoffset(first)


def test_overflow_numeric_values_do_not_interrupt_summary(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "resourceLogs": [
            {
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "attributes": [
                                    {"key": "event.name", "value": {"stringValue": "user_prompt"}},
                                    {"key": "prompt_length", "value": {"doubleValue": 10**400}},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    metrics: dict[str, object] = {
        "resourceMetrics": [
            {
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "claude_code.commit.count",
                                "sum": {
                                    "aggregationTemporality": 1,
                                    "dataPoints": [{"asDouble": 10**400, "startTimeUnixNano": 1, "timeUnixNano": 2}],
                                },
                            }
                        ]
                    }
                ]
            }
        ]
    }
    path = tmp_path / "overflow.jsonl"
    path.write_text(
        json.dumps(envelope(signal="logs", payload=payload))
        + "\n"
        + json.dumps(envelope(signal="metrics", payload=metrics))
        + "\n",
        encoding="utf-8",
    )
    summary = summarize_capture(path)
    assert summary.sessions.prompts == 1
    assert summary.activity.commits == 0
    assert summary.coverage.unknown_otlp_values >= 2
