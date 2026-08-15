import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coding_agent_performance.trace.capture import CaptureEnvelope, CaptureError
from coding_agent_performance.trace.model import (
    ActivityMeasurement,
    ModelRequest,
    NamedLifecycleEvent,
    ToolExecution,
)
from coding_agent_performance.trace.render import render_json, render_text
from coding_agent_performance.trace.summary import (
    IncrementalSummarizer,
    duration_stats,
    nearest_rank,
    summarize_capture,
)
from tests.helpers.otlp import envelope, number_point, resource_logs, resource_metrics, sum_metric
from tests.helpers.synthetic_capture import FIXTURE_PATH, SENSITIVE_MARKERS, write_synthetic_capture


def _envelope(
    signal: str, payload: dict[str, object], received_at: str = "2026-08-15T10:00:00+00:00"
) -> CaptureEnvelope:
    row = envelope(signal=signal, payload=payload, received_at=received_at)
    return CaptureEnvelope(
        schema_version=1,
        received_at=datetime.fromisoformat(str(row["received_at"])),
        source="claude-code",
        signal=signal,
        payload=payload,
    )


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
    assert summary.activity.active_time_seconds == {"user": 20.0, "cli": 40.0}
    assert summary.coverage.duplicate_log_records == 1
    assert summary.coverage.duplicate_metric_points == 1
    assert summary.coverage.unsupported_metric_points == 1
    assert summary.coverage.unknown_events == {"weird_event": 1}
    assert "custom.unknown.metric" in summary.coverage.unknown_metrics
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


def test_delta_metrics_are_summed() -> None:
    summarizer = IncrementalSummarizer(filename="delta.jsonl")
    first = ActivityMeasurement(
        name="claude_code.commit.count",
        value=2,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=10,
        aggregation_temporality="delta",
        kind="sum",
    )
    second = ActivityMeasurement(
        name="claude_code.commit.count",
        value=3,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=20,
        aggregation_temporality="delta",
        kind="sum",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (first, second), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("delta.jsonl")).activity.commits == 5


def test_cumulative_uses_latest_timestamp_not_max_value() -> None:
    summarizer = IncrementalSummarizer(filename="cum.jsonl")
    older = ActivityMeasurement(
        name="claude_code.commit.count",
        value=9,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=10,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    newer = ActivityMeasurement(
        name="claude_code.commit.count",
        value=3,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=20,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (older, newer), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("cum.jsonl")).activity.commits == 3


def test_counter_reset_uses_start_time_identity() -> None:
    summarizer = IncrementalSummarizer(filename="reset.jsonl")
    first = ActivityMeasurement(
        name="claude_code.commit.count",
        value=4,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=10,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    reset = ActivityMeasurement(
        name="claude_code.commit.count",
        value=2,
        unit="",
        attributes={},
        start_time_unix_nano=99,
        time_unix_nano=20,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (first, reset), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("reset.jsonl")).activity.commits == 6


def test_missing_temporality_uses_latest_and_warns() -> None:
    summarizer = IncrementalSummarizer(filename="tmp.jsonl")
    first = ActivityMeasurement(
        name="claude_code.commit.count",
        value=1,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=10,
        aggregation_temporality=None,
        kind="sum",
    )
    second = ActivityMeasurement(
        name="claude_code.commit.count",
        value=8,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=20,
        aggregation_temporality=None,
        kind="sum",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (first, second), log_count=0, metric_count=2, unsupported=0
    )
    summary = summarizer.finish(Path("tmp.jsonl"))
    assert summary.activity.commits == 8
    assert summary.coverage.warnings == (
        "missing or unknown aggregation temporality; using latest datapoint per series",
    )


def test_duplicate_logs_are_ignored() -> None:
    request = ModelRequest(
        session_id="session-a",
        prompt_id="prompt-a",
        model="claude-example",
        query_source="main",
        duration_ms=10,
        input_tokens=1,
        output_tokens=1,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        estimated_cost_usd_micros=1,
        event_sequence=1,
    )
    summarizer = IncrementalSummarizer(filename="dup.jsonl")
    summarizer.add(_envelope("logs", resource_logs([])), (request, request), log_count=2, metric_count=0, unsupported=0)
    summary = summarizer.finish(Path("dup.jsonl"))
    assert summary.model_usage.requests == 1
    assert summary.coverage.duplicate_log_records == 1


def test_incomplete_identity_is_not_deduplicated() -> None:
    first = ModelRequest(
        session_id=None,
        prompt_id=None,
        model="claude-example",
        query_source="main",
        duration_ms=10,
        input_tokens=1,
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        estimated_cost_usd_micros=1,
        event_sequence=None,
    )
    summarizer = IncrementalSummarizer(filename="nodedup.jsonl")
    summarizer.add(_envelope("logs", resource_logs([])), (first, first), log_count=2, metric_count=0, unsupported=0)
    assert summarizer.finish(Path("nodedup.jsonl")).model_usage.requests == 2


def test_percentiles() -> None:
    assert nearest_rank([], 0.5) is None
    assert nearest_rank([7], 0.5) == 7
    assert nearest_rank([7], 0.95) == 7
    assert nearest_rank([600, 900, 1000, 1500], 0.50) == 900
    assert nearest_rank([600, 900, 1000, 1500], 0.95) == 1500
    empty = duration_stats([])
    assert empty.average is None
    assert empty.p50 is None
    single = duration_stats([250])
    assert single.total == 250
    assert single.average == 250.0
    assert single.p50 == 250
    assert single.p95 == 250


def test_empty_recognized_data_fails(tmp_path: Path) -> None:
    path = tmp_path / "empty-data.jsonl"
    path.write_text(json.dumps(envelope(signal="logs", payload=resource_logs([]))) + "\n", encoding="utf-8")
    with pytest.raises(CaptureError, match="no recognized telemetry"):
        summarize_capture(path)


def test_json_and_text_are_deterministic_and_private() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    text = render_text(summary)
    payload = render_json(summary)
    parsed = json.loads(payload)
    assert json.dumps(parsed, allow_nan=False)
    assert parsed["schema_version"] == 1
    assert parsed["capture"]["file"] == "synthetic-capture.jsonl"
    assert "Model usage" in text
    assert "$0.012345" in text
    for marker in SENSITIVE_MARKERS:
        assert marker not in text
        assert marker not in payload


def test_fixture_writer_roundtrip(tmp_path: Path) -> None:
    path = write_synthetic_capture(tmp_path / "copy.jsonl")
    assert summarize_capture(path).model_usage.requests == 4


def test_lifecycle_and_empty_optional_fields() -> None:
    summarizer = IncrementalSummarizer(filename="life.jsonl")
    records = (
        NamedLifecycleEvent(name="api_refusal", session_id="s", event_sequence=1),
        NamedLifecycleEvent(name="compaction", session_id="s", event_sequence=2),
        NamedLifecycleEvent(name="subagent_completed", session_id="s", event_sequence=3),
        NamedLifecycleEvent(name="tool_decision", session_id="s", event_sequence=4),
        ModelRequest(
            session_id="s",
            prompt_id=None,
            model="claude-example",
            query_source=None,
            duration_ms=None,
            input_tokens=1,
            output_tokens=0,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            estimated_cost_usd_micros=0,
            event_sequence=5,
        ),
        ToolExecution(
            session_id="s",
            prompt_id=None,
            tool_name="Read",
            success=True,
            duration_ms=None,
            input_size_bytes=None,
            result_size_bytes=None,
            error_type=None,
            tool_use_id=None,
            event_sequence=6,
        ),
        ActivityMeasurement(
            name="claude_code.lines_of_code.count",
            value=3,
            unit="",
            attributes={"type": "added"},
            start_time_unix_nano=1,
            time_unix_nano=None,
            aggregation_temporality="delta",
            kind="sum",
        ),
        ActivityMeasurement(
            name="claude_code.pull_request.count",
            value=1,
            unit="",
            attributes={},
            start_time_unix_nano=1,
            time_unix_nano=5,
            aggregation_temporality="delta",
            kind="sum",
        ),
        ActivityMeasurement(
            name="claude_code.code_edit_tool.decision",
            value=2,
            unit="",
            attributes={"decision": "reject"},
            start_time_unix_nano=1,
            time_unix_nano=6,
            aggregation_temporality="delta",
            kind="sum",
        ),
        ActivityMeasurement(
            name="claude_code.commit.count",
            value=1,
            unit="",
            attributes={},
            start_time_unix_nano=1,
            time_unix_nano=1,
            aggregation_temporality="cumulative",
            kind="sum",
        ),
        ActivityMeasurement(
            name="claude_code.commit.count",
            value=9,
            unit="",
            attributes={},
            start_time_unix_nano=1,
            time_unix_nano=0,
            aggregation_temporality="cumulative",
            kind="sum",
        ),
    )
    summarizer.add(_envelope("logs", resource_logs([])), records, log_count=6, metric_count=5, unsupported=0)
    summary = summarizer.finish(Path("life.jsonl"))
    assert summary.model_usage.refusals == 1
    assert summary.sessions.compactions == 1
    assert summary.sessions.subagents_completed == 1
    assert summary.activity.lines_of_code["added"] == 3
    assert summary.activity.pull_requests == 1
    assert summary.activity.code_edit_decisions["rejected"] == 2
    assert summary.activity.commits == 1
    text = render_text(summary)
    assert "$0.000000" in text
    assert "n/a" in text


def test_known_timestamp_wins_over_missing_when_known_is_first() -> None:
    summarizer = IncrementalSummarizer(filename="ts.jsonl")
    known = ActivityMeasurement(
        name="claude_code.commit.count",
        value=3,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=10,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    missing = ActivityMeasurement(
        name="claude_code.commit.count",
        value=99,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=None,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (known, missing), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("ts.jsonl")).activity.commits == 3


def test_known_timestamp_wins_over_missing_when_missing_is_first() -> None:
    summarizer = IncrementalSummarizer(filename="ts.jsonl")
    missing = ActivityMeasurement(
        name="claude_code.commit.count",
        value=99,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=None,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    known = ActivityMeasurement(
        name="claude_code.commit.count",
        value=3,
        unit="",
        attributes={},
        start_time_unix_nano=1,
        time_unix_nano=10,
        aggregation_temporality="cumulative",
        kind="sum",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (missing, known), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("ts.jsonl")).activity.commits == 3


def test_tool_average_uses_only_observed_durations() -> None:
    summarizer = IncrementalSummarizer(filename="tools.jsonl")
    observed = ToolExecution(
        session_id=None,
        prompt_id=None,
        tool_name="Bash",
        success=True,
        duration_ms=400,
        input_size_bytes=1,
        result_size_bytes=1,
        error_type=None,
        tool_use_id=None,
        event_sequence=1,
    )
    missing = ToolExecution(
        session_id=None,
        prompt_id=None,
        tool_name="Bash",
        success=True,
        duration_ms=None,
        input_size_bytes=1,
        result_size_bytes=1,
        error_type=None,
        tool_use_id=None,
        event_sequence=2,
    )
    summarizer.add(
        _envelope("logs", resource_logs([])), (observed, missing), log_count=2, metric_count=0, unsupported=0
    )
    bash = summarizer.finish(Path("tools.jsonl")).tools.by_name[0]
    assert bash.calls == 2
    assert bash.duration_ms_total == 400
    assert bash.duration_ms_average == 400.0


def test_unknown_otlp_values_are_accumulated_and_rendered() -> None:
    summarizer = IncrementalSummarizer(filename="unknown.jsonl")
    tool = ToolExecution(
        session_id=None,
        prompt_id=None,
        tool_name="Read",
        success=True,
        duration_ms=1,
        input_size_bytes=1,
        result_size_bytes=1,
        error_type=None,
        tool_use_id=None,
        event_sequence=1,
    )
    summarizer.add(
        _envelope("logs", resource_logs([])),
        (tool,),
        log_count=1,
        metric_count=0,
        unsupported=0,
        unknown_otlp_values=2,
    )
    summarizer.add(
        _envelope("logs", resource_logs([])),
        (),
        log_count=0,
        metric_count=0,
        unsupported=0,
        unknown_otlp_values=3,
    )
    summary = summarizer.finish(Path("unknown.jsonl"))
    assert summary.coverage.unknown_otlp_values == 5
    assert '"unknown_otlp_values": 5' in render_json(summary)
    assert "Unknown OTLP values: 5" in render_text(summary)


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
