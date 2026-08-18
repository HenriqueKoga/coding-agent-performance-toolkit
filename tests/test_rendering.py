import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from coding_agent_performance.trace.aggregation import IncrementalSummarizer
from coding_agent_performance.trace.capture import CaptureEnvelope
from coding_agent_performance.trace.insights import HIGH_TOOL_RESULT_VOLUME_THRESHOLD
from coding_agent_performance.trace.records import ActivityMeasurement, NamedLifecycleEvent, ToolExecution
from coding_agent_performance.trace.rendering import (
    escape_filename,
    format_utc_timestamp,
    render_capture_list,
    render_capture_listing,
    render_json,
    render_text,
    summary_to_dict,
)
from coding_agent_performance.trace.report import TraceSummary
from coding_agent_performance.trace.storage import CaptureListing
from coding_agent_performance.trace.summary import summarize_capture
from tests.helpers.otlp import envelope, number_point, resource_logs, resource_metrics, sum_metric
from tests.helpers.synthetic_capture import FIXTURE_PATH, SENSITIVE_MARKERS


def _envelope(signal: str, payload: dict[str, object]) -> CaptureEnvelope:
    return CaptureEnvelope(
        schema_version=1,
        received_at=datetime.fromisoformat("2026-08-15T10:00:00+00:00"),
        source="claude-code",
        signal=signal,
        payload=payload,
    )


def _tool_execution(
    tool_name: str,
    *,
    success: bool,
    event_sequence: int,
    session_id: str | None = None,
    prompt_id: str | None = None,
    error_type: str | None = None,
    tool_use_id: str | None = None,
    result_size_bytes: int = 200,
) -> ToolExecution:
    return ToolExecution(
        session_id=session_id,
        prompt_id=prompt_id,
        tool_name=tool_name,
        success=success,
        duration_ms=10,
        input_size_bytes=100,
        result_size_bytes=result_size_bytes,
        error_type=error_type,
        tool_use_id=tool_use_id,
        event_sequence=event_sequence,
    )


def _add_tools(summarizer: IncrementalSummarizer, *records: ToolExecution) -> None:
    for record in records:
        summarizer.add(
            _envelope("logs", resource_logs([])),
            (record,),
            log_count=1,
            metric_count=0,
            unsupported=0,
        )


def _finish_tools(*records: ToolExecution, filename: str) -> TraceSummary:
    summarizer = IncrementalSummarizer(filename=filename)
    _add_tools(summarizer, *records)
    return summarizer.finish(Path(filename))


def _compaction_event(event_sequence: int, *, session_id: str | None = "session-test") -> NamedLifecycleEvent:
    return NamedLifecycleEvent(name="compaction", session_id=session_id, event_sequence=event_sequence)


def _subagent_event(event_sequence: int, *, session_id: str | None = "session-test") -> NamedLifecycleEvent:
    return NamedLifecycleEvent(name="subagent_completed", session_id=session_id, event_sequence=event_sequence)


def _finish_records(*records: ToolExecution | NamedLifecycleEvent, filename: str) -> TraceSummary:
    summarizer = IncrementalSummarizer(filename=filename)
    for record in records:
        summarizer.add(
            _envelope("logs", resource_logs([])),
            (record,),
            log_count=1,
            metric_count=0,
            unsupported=0,
        )
    return summarizer.finish(Path(filename))


def _assert_markers_absent(text: str, payload: str, *markers: str) -> None:
    for marker in markers:
        assert marker not in text
        assert marker not in payload


def test_json_and_text_are_deterministic_and_private() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    text = render_text(summary)
    payload = render_json(summary)
    parsed = json.loads(payload)
    assert json.dumps(parsed, allow_nan=False)
    assert parsed["schema_version"] == 1
    assert parsed["capture"]["file"] == "synthetic-capture.jsonl"
    assert parsed["activity"]["active_time_seconds"] == {"user": 20.0, "cli": 40.0}
    assert parsed["activity"]["lines_of_code"] == {"added": 0, "removed": 0}
    assert "Model usage" in text
    assert "Usage source:    API request events" in text
    assert "$0.012345" in text
    for marker in SENSITIVE_MARKERS:
        assert marker not in text
        assert marker not in payload


def test_json_allowlist_keeps_v1_activity_keys() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    payload = summary_to_dict(summary)
    activity = payload["activity"]
    assert isinstance(activity, dict)
    assert set(activity) == {
        "active_time_seconds",
        "lines_of_code",
        "commits",
        "pull_requests",
        "code_edit_decisions",
    }
    assert set(activity["active_time_seconds"]) == {"user", "cli"}
    assert set(activity["lines_of_code"]) == {"added", "removed"}
    assert set(activity["code_edit_decisions"]) == {"accepted", "rejected"}


def test_json_allowlist_keeps_tool_health_keys() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    payload = summary_to_dict(summary)
    tools = payload["tools"]
    assert isinstance(tools, dict)
    assert set(tools) == {
        "calls",
        "successes",
        "failures",
        "success_rate_bps",
        "input_bytes",
        "result_bytes",
        "duration_ms",
        "by_name",
    }
    assert tools["calls"] == 3
    assert tools["successes"] == 2
    assert tools["failures"] == 1
    assert tools["success_rate_bps"] == 6666
    bash = next(row for row in tools["by_name"] if row["name"] == "Bash")
    assert bash["success_rate"] == 0.5
    assert "success_rate_bps" not in bash


def test_json_allowlist_keeps_insight_keys() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    payload = summary_to_dict(summary)
    insights = payload["insights"]
    assert isinstance(insights, dict)
    assert set(insights) == {
        "repeated_tool_calls",
        "repeated_failed_tool_calls",
        "high_tool_result_volume",
        "high_tool_failure_rate",
        "dominant_tool",
        "compaction_pressure",
        "subagent_usage",
    }
    assert insights["repeated_failed_tool_calls"] == []
    assert insights["high_tool_result_volume"] == []
    assert insights["high_tool_failure_rate"] == []
    assert insights["dominant_tool"] is None
    assert insights["compaction_pressure"] is None
    assert insights["subagent_usage"] is None


def test_text_usage_source_labels() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    assert "Usage source:    API request events" in render_text(summary)


def test_text_usage_source_otel_metrics(tmp_path: Path) -> None:
    payload = resource_metrics(
        [
            sum_metric(
                "claude_code.token.usage",
                [number_point(value=3, attributes={"type": "input", "model": "claude-example"})],
                temporality=1,
            )
        ]
    )
    path = tmp_path / "otel.jsonl"
    path.write_text(json.dumps(envelope(signal="metrics", payload=payload)) + "\n", encoding="utf-8")
    text = render_text(summarize_capture(path))
    assert "Usage source:    OpenTelemetry metrics" in text


def test_text_usage_source_none() -> None:
    summarizer = IncrementalSummarizer(filename="none.jsonl")
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
    summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    text = render_text(summarizer.finish(Path("none.jsonl")))
    assert "Usage source:    none" in text


def test_tool_table_fits_long_names() -> None:
    summarizer = IncrementalSummarizer(filename="tools.jsonl")
    long_name = "ReadManyFiles"
    tool = ToolExecution(
        session_id=None,
        prompt_id=None,
        tool_name=long_name,
        success=True,
        duration_ms=25,
        input_size_bytes=1,
        result_size_bytes=1,
        error_type=None,
        tool_use_id=None,
        event_sequence=1,
    )
    summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    text = render_text(summarizer.finish(Path("tools.jsonl")))
    assert long_name in text
    assert "Calls" in text


def test_tool_table_truncates_names_over_width() -> None:
    summarizer = IncrementalSummarizer(filename="tools.jsonl")
    long_name = "ReadManyFilesWithAnOverlongSyntheticName"
    tool = ToolExecution(
        session_id=None,
        prompt_id=None,
        tool_name=long_name,
        success=True,
        duration_ms=25,
        input_size_bytes=1,
        result_size_bytes=1,
        error_type=None,
        tool_use_id=None,
        event_sequence=1,
    )
    summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    summary = summarizer.finish(Path("tools.jsonl"))
    text = render_text(summary)
    truncated = f"{long_name[:21]}..."
    assert truncated in text
    assert long_name not in text
    assert json.loads(render_json(summary))["tools"]["by_name"][0]["name"] == long_name


def test_unknown_otlp_values_are_rendered() -> None:
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
        unknown_otlp_values=5,
    )
    summary = summarizer.finish(Path("unknown.jsonl"))
    assert '"unknown_otlp_values": 5' in render_json(summary)
    assert "Unknown OTLP values: 5" in render_text(summary)


def test_zero_cost_and_missing_durations_render_placeholders() -> None:
    summarizer = IncrementalSummarizer(filename="life.jsonl")
    tool = ToolExecution(
        session_id="s",
        prompt_id=None,
        tool_name="Read",
        success=True,
        duration_ms=None,
        input_size_bytes=None,
        result_size_bytes=None,
        error_type=None,
        tool_use_id=None,
        event_sequence=1,
    )
    summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    text = render_text(summarizer.finish(Path("life.jsonl")))
    assert "$0.000000" in text
    assert "n/a" in text


def test_escape_filename_keeps_one_logical_line() -> None:
    escaped = escape_filename("bad\nname\twith\rcr\x1b[31m.jsonl")
    assert "\n" not in escaped
    assert "\r" not in escaped
    assert "\t" not in escaped
    assert "\x1b" not in escaped
    assert escaped == "bad\\nname\\twith\\rcr\\x1b[31m.jsonl"


def test_escape_filename_handles_unicode_separators_and_backslashes() -> None:
    escaped = escape_filename("a\\b\u2028c\u2029d\x85e\U000e0001.jsonl")
    assert escaped == "a\\\\b\\u2028c\\u2029d\\x85e\\U000e0001.jsonl"
    assert "\u2028" not in escaped
    assert "\u2029" not in escaped
    assert "\x85" not in escaped
    assert "\U000e0001" not in escaped


def test_render_capture_list_empty() -> None:
    assert render_capture_list(()) == "No capture files found."


def test_render_capture_listing_is_deterministic() -> None:
    listing = CaptureListing(
        name="capture.jsonl",
        size_bytes=42,
        modified_at=datetime(2026, 8, 17, 16, 25, 9, tzinfo=UTC),
    )
    assert render_capture_listing(listing) == "capture.jsonl  42  2026-08-17T16:25:09Z"
    assert format_utc_timestamp(listing.modified_at).endswith("Z")


def test_format_utc_timestamp_normalizes_offset_to_z() -> None:
    value = datetime(2026, 8, 17, 13, 25, 9, tzinfo=timezone(timedelta(hours=-3)))
    assert format_utc_timestamp(value) == "2026-08-17T16:25:09Z"


def test_insights_appear_in_text_when_findings_exist() -> None:
    text = render_text(
        _finish_tools(
            *(_tool_execution("Read", success=True, event_sequence=1) for _ in range(5)),
            filename="insights.jsonl",
        )
    )
    assert "Insights" in text
    assert "Repeated tool calls" in text
    assert "- Read: 5 calls" in text


def test_insights_not_present_when_no_findings() -> None:
    text = render_text(
        _finish_tools(
            _tool_execution("Read", success=True, event_sequence=1),
            filename="no-insights.jsonl",
        )
    )
    assert "Insights" not in text


def test_insights_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                *(_tool_execution("Read", success=True, event_sequence=i) for i in range(8)),
                filename="insights.jsonl",
            )
        )
    )
    assert "insights" in parsed
    assert "repeated_tool_calls" in parsed["insights"]
    findings = parsed["insights"]["repeated_tool_calls"]
    assert len(findings) == 1
    assert findings[0]["tool_name"] == "Read"
    assert findings[0]["call_count"] == 8
    assert parsed["insights"]["repeated_failed_tool_calls"] == []
    assert parsed["insights"]["high_tool_result_volume"] == []
    assert parsed["insights"]["high_tool_failure_rate"] == []


def test_insights_multiple_repeated_tools_ordered() -> None:
    records = [
        _tool_execution(tool_name, success=True, event_sequence=index)
        for tool_name, count in (("Zebra", 5), ("Apple", 4), ("Mango", 3))
        for index in range(count)
    ]
    text = render_text(_finish_tools(*records, filename="multi-insights.jsonl"))
    assert "- Apple: 4 calls" in text
    assert "- Mango: 3 calls" in text
    assert "- Zebra: 5 calls" in text
    apple_pos = text.index("- Apple: 4 calls")
    mango_pos = text.index("- Mango: 3 calls")
    zebra_pos = text.index("- Zebra: 5 calls")
    assert apple_pos < mango_pos < zebra_pos


def test_insights_contain_only_safe_evidence() -> None:
    summary = _finish_tools(
        *(
            _tool_execution(
                "Read",
                success=True,
                event_sequence=i,
                session_id="secret-session-id",
                prompt_id="secret-prompt-id",
                tool_use_id="secret-tool-id",
            )
            for i in range(5)
        ),
        filename="privacy.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    _assert_markers_absent(text, payload, "secret-session-id", "secret-prompt-id", "secret-tool-id")
    parsed = json.loads(payload)
    for finding in parsed["insights"]["repeated_tool_calls"]:
        assert set(finding.keys()) == {"tool_name", "call_count"}
    assert parsed["insights"]["repeated_failed_tool_calls"] == []
    assert parsed["insights"]["high_tool_result_volume"] == []
    assert parsed["insights"]["high_tool_failure_rate"] == []


def test_repeated_failed_insights_appear_in_text() -> None:
    text = render_text(
        _finish_tools(
            *(_tool_execution("Bash", success=False, event_sequence=i, error_type="ShellError") for i in range(4)),
            filename="failed-insights.jsonl",
        )
    )
    assert "Insights" in text
    assert "Repeated failed tool calls" in text
    assert "- Bash: 4 failures" in text
    assert "ShellError" not in text


def test_repeated_failed_insights_not_present_when_only_successes() -> None:
    summary = _finish_tools(
        *(_tool_execution("Bash", success=True, event_sequence=i) for i in range(5)),
        filename="success-only.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Repeated tool calls" in text
    assert "Repeated failed tool calls" not in text
    assert parsed["insights"]["repeated_failed_tool_calls"] == []


def test_repeated_failed_insights_not_present_below_threshold() -> None:
    summary = _finish_tools(
        *(_tool_execution("Bash", success=False, event_sequence=i) for i in range(2)),
        filename="below-failed.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Repeated failed tool calls" not in text
    assert parsed["insights"]["repeated_failed_tool_calls"] == []


def test_repeated_failed_insights_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                *(_tool_execution("Bash", success=False, event_sequence=i) for i in range(4)),
                filename="failed-insights.jsonl",
            )
        )
    )
    findings = parsed["insights"]["repeated_failed_tool_calls"]
    assert findings == [{"tool_name": "Bash", "failure_count": 4}]


def test_repeated_failed_insights_mixed_success_and_failure() -> None:
    summary = _finish_tools(
        *(_tool_execution("Bash", success=True, event_sequence=i) for i in range(4)),
        *(_tool_execution("Bash", success=False, event_sequence=i + 4) for i in range(3)),
        filename="mixed-failed.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "- Bash: 7 calls" in text
    assert "- Bash: 3 failures" in text
    assert parsed["insights"]["repeated_tool_calls"] == [{"tool_name": "Bash", "call_count": 7}]
    assert parsed["insights"]["repeated_failed_tool_calls"] == [{"tool_name": "Bash", "failure_count": 3}]


def test_repeated_failed_insights_multiple_tools_ordered() -> None:
    records = [
        _tool_execution(tool_name, success=False, event_sequence=index)
        for tool_name, count in (("Zebra", 5), ("Apple", 4), ("Mango", 3))
        for index in range(count)
    ]
    summary = _finish_tools(*records, filename="multi-failed.jsonl")
    text = render_text(summary)
    payload = render_json(summary)
    assert "- Apple: 4 failures" in text
    assert "- Mango: 3 failures" in text
    assert "- Zebra: 5 failures" in text
    apple_pos = text.index("- Apple: 4 failures")
    mango_pos = text.index("- Mango: 3 failures")
    zebra_pos = text.index("- Zebra: 5 failures")
    assert apple_pos < mango_pos < zebra_pos
    parsed = json.loads(payload)
    assert [finding["tool_name"] for finding in parsed["insights"]["repeated_failed_tool_calls"]] == [
        "Apple",
        "Mango",
        "Zebra",
    ]
    assert render_text(summary) == text
    assert render_json(summary) == payload


def test_repeated_failed_insights_contain_only_safe_evidence() -> None:
    summary = _finish_tools(
        *(
            _tool_execution(
                "Bash",
                success=False,
                event_sequence=i,
                session_id="secret-session-id",
                prompt_id="secret-prompt-id",
                error_type="ShellError",
                tool_use_id="secret-tool-id",
            )
            for i in range(4)
        ),
        filename="failed-privacy.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    _assert_markers_absent(
        text,
        payload,
        "secret-session-id",
        "secret-prompt-id",
        "secret-tool-id",
        "ShellError",
        "traceback",
        "rm -rf",
        "/tmp/",
    )
    parsed = json.loads(payload)
    for finding in parsed["insights"]["repeated_failed_tool_calls"]:
        assert set(finding.keys()) == {"tool_name", "failure_count"}


def test_high_tool_result_volume_appears_in_text() -> None:
    text = render_text(
        _finish_tools(
            _tool_execution("Read", success=True, event_sequence=0, result_size_bytes=196608),
            filename="volume-insights.jsonl",
        )
    )
    assert "Insights" in text
    assert "High tool result volume" in text
    assert "- Read: 196608 result bytes" in text


def test_high_tool_result_volume_not_present_below_threshold() -> None:
    summary = _finish_tools(
        _tool_execution(
            "Read",
            success=True,
            event_sequence=0,
            result_size_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD - 1,
        ),
        filename="volume-below.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "High tool result volume" not in text
    assert parsed["insights"]["high_tool_result_volume"] == []


def test_high_tool_result_volume_not_present_when_zero_bytes() -> None:
    summary = _finish_tools(
        _tool_execution("Read", success=True, event_sequence=0, result_size_bytes=0),
        filename="volume-zero.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "High tool result volume" not in text
    assert parsed["insights"]["high_tool_result_volume"] == []


def test_high_tool_result_volume_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                _tool_execution("Read", success=True, event_sequence=0, result_size_bytes=196608),
                filename="volume-insights.jsonl",
            )
        )
    )
    findings = parsed["insights"]["high_tool_result_volume"]
    assert findings == [{"tool_name": "Read", "result_bytes": 196608}]


def test_high_tool_result_volume_at_threshold_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                _tool_execution(
                    "Read",
                    success=True,
                    event_sequence=0,
                    result_size_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD,
                ),
                filename="volume-at-threshold.jsonl",
            )
        )
    )
    assert parsed["insights"]["high_tool_result_volume"] == [
        {"tool_name": "Read", "result_bytes": HIGH_TOOL_RESULT_VOLUME_THRESHOLD}
    ]


def test_high_tool_result_volume_multiple_tools_ordered() -> None:
    summary = _finish_tools(
        _tool_execution("Zebra", success=True, event_sequence=0, result_size_bytes=196608),
        _tool_execution("Apple", success=True, event_sequence=1, result_size_bytes=147456),
        _tool_execution("Mango", success=True, event_sequence=2, result_size_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD),
        filename="multi-volume.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    assert "- Apple: 147456 result bytes" in text
    assert f"- Mango: {HIGH_TOOL_RESULT_VOLUME_THRESHOLD} result bytes" in text
    assert "- Zebra: 196608 result bytes" in text
    apple_pos = text.index("- Apple: 147456 result bytes")
    mango_pos = text.index(f"- Mango: {HIGH_TOOL_RESULT_VOLUME_THRESHOLD} result bytes")
    zebra_pos = text.index("- Zebra: 196608 result bytes")
    assert apple_pos < mango_pos < zebra_pos
    parsed = json.loads(payload)
    assert [finding["tool_name"] for finding in parsed["insights"]["high_tool_result_volume"]] == [
        "Apple",
        "Mango",
        "Zebra",
    ]
    assert render_text(summary) == text
    assert render_json(summary) == payload


def test_high_tool_result_volume_coexists_with_existing_insights() -> None:
    summary = _finish_tools(
        *(_tool_execution("Read", success=True, event_sequence=i, result_size_bytes=65536) for i in range(3)),
        *(
            _tool_execution(
                "Bash",
                success=False,
                event_sequence=i + 3,
                error_type="ShellError",
                result_size_bytes=0,
            )
            for i in range(3)
        ),
        filename="coexist-insights.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "- Bash: 3 calls" in text
    assert "- Read: 3 calls" in text
    assert "- Bash: 3 failures" in text
    assert "- Read: 196608 result bytes" in text
    assert parsed["insights"]["repeated_tool_calls"] == [
        {"tool_name": "Bash", "call_count": 3},
        {"tool_name": "Read", "call_count": 3},
    ]
    assert parsed["insights"]["repeated_failed_tool_calls"] == [{"tool_name": "Bash", "failure_count": 3}]
    assert parsed["insights"]["high_tool_result_volume"] == [{"tool_name": "Read", "result_bytes": 196608}]
    assert parsed["insights"]["high_tool_failure_rate"] == [
        {
            "tool_name": "Bash",
            "failed_calls": 3,
            "total_calls": 3,
            "failure_rate": {"numerator": 1, "denominator": 1},
        }
    ]
    assert "- Bash: 3 failed of 3 calls (1/1)" in text


def test_high_tool_result_volume_contains_only_safe_evidence() -> None:
    summary = _finish_tools(
        _tool_execution(
            "Read",
            success=True,
            event_sequence=0,
            session_id="secret-session-id",
            prompt_id="secret-prompt-id",
            tool_use_id="secret-tool-id",
            result_size_bytes=196608,
        ),
        filename="volume-privacy.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    _assert_markers_absent(
        text,
        payload,
        "secret-session-id",
        "secret-prompt-id",
        "secret-tool-id",
        "file contents",
        "/tmp/",
        "arguments",
    )
    parsed = json.loads(payload)
    for finding in parsed["insights"]["high_tool_result_volume"]:
        assert set(finding.keys()) == {"tool_name", "result_bytes"}
        assert isinstance(finding["result_bytes"], int)


def _activity_only_summary(filename: str) -> IncrementalSummarizer:
    summarizer = IncrementalSummarizer(filename=filename)
    measurement = ActivityMeasurement(
        name="claude_code.commit.count",
        value=1,
        unit="",
        attributes=(),
        start_time_unix_nano=1,
        time_unix_nano=2,
        aggregation_temporality="delta",
        kind="sum",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])),
        (measurement,),
        log_count=0,
        metric_count=1,
        unsupported=0,
    )
    return summarizer


def test_zero_tool_calls_render_explicit_safe_rate() -> None:
    summary = _activity_only_summary("zero-tools.jsonl").finish(Path("zero-tools.jsonl"))
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert parsed["tools"]["calls"] == 0
    assert parsed["tools"]["successes"] == 0
    assert parsed["tools"]["failures"] == 0
    assert parsed["tools"]["success_rate_bps"] is None
    assert "Successes:       0" in text
    assert "Failures:        0" in text
    assert "Success rate:    n/a" in text
    assert "NaN" not in text
    assert "Infinity" not in render_json(summary)
    assert parsed["insights"] == {
        "repeated_tool_calls": [],
        "repeated_failed_tool_calls": [],
        "high_tool_result_volume": [],
        "high_tool_failure_rate": [],
        "dominant_tool": None,
        "compaction_pressure": None,
        "subagent_usage": None,
    }


def test_all_successful_calls_render_full_rate() -> None:
    summary = _finish_tools(
        *(_tool_execution("Read", success=True, event_sequence=i) for i in range(3)),
        filename="all-success.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert parsed["tools"]["calls"] == 3
    assert parsed["tools"]["successes"] == 3
    assert parsed["tools"]["failures"] == 0
    assert parsed["tools"]["success_rate_bps"] == 10_000
    assert "Successes:       3" in text
    assert "Failures:        0" in text
    assert "Success rate:    100.00%" in text
    assert parsed["insights"]["repeated_tool_calls"] == [{"tool_name": "Read", "call_count": 3}]
    assert parsed["insights"]["repeated_failed_tool_calls"] == []


def test_all_failed_calls_render_zero_rate() -> None:
    summary = _finish_tools(
        *(_tool_execution("Bash", success=False, event_sequence=i) for i in range(2)),
        filename="all-failed.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert parsed["tools"]["calls"] == 2
    assert parsed["tools"]["successes"] == 0
    assert parsed["tools"]["failures"] == 2
    assert parsed["tools"]["success_rate_bps"] == 0
    assert "Successes:       0" in text
    assert "Failures:        2" in text
    assert "Success rate:    0.00%" in text
    assert parsed["insights"]["repeated_failed_tool_calls"] == []


def test_mixed_calls_render_exact_counts_and_stable_rate() -> None:
    summary = _finish_tools(
        _tool_execution("Read", success=True, event_sequence=0),
        _tool_execution("Read", success=True, event_sequence=1),
        _tool_execution("Bash", success=False, event_sequence=2),
        filename="mixed-health.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    parsed = json.loads(payload)
    assert parsed["tools"]["calls"] == 3
    assert parsed["tools"]["successes"] == 2
    assert parsed["tools"]["failures"] == 1
    assert parsed["tools"]["success_rate_bps"] == 6666
    assert "Successes:       2" in text
    assert "Failures:        1" in text
    assert "Success rate:    66.66%" in text
    assert render_text(summary) == text
    assert render_json(summary) == payload
    bash = next(row for row in parsed["tools"]["by_name"] if row["name"] == "Bash")
    read = next(row for row in parsed["tools"]["by_name"] if row["name"] == "Read")
    assert bash["success_rate"] == 0.0
    assert read["success_rate"] == 1.0
    assert parsed["insights"] == {
        "repeated_tool_calls": [],
        "repeated_failed_tool_calls": [],
        "high_tool_result_volume": [],
        "high_tool_failure_rate": [],
        "dominant_tool": None,
        "compaction_pressure": None,
        "subagent_usage": None,
    }


def test_tool_health_text_and_json_agree_on_fixture() -> None:
    summary = summarize_capture(FIXTURE_PATH)
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert parsed["tools"]["success_rate_bps"] == 6666
    assert "Success rate:    66.66%" in text
    assert parsed["tools"]["calls"] == summary.tools.calls
    assert parsed["tools"]["successes"] == summary.tools.successes
    assert parsed["tools"]["failures"] == summary.tools.failures
    assert "quality" not in text.lower()
    assert "health score" not in text.lower()
    assert "grade" not in text.lower()


def test_high_tool_failure_rate_appears_in_text() -> None:
    text = render_text(
        _finish_tools(
            *(_tool_execution("Bash", success=True, event_sequence=i) for i in range(2)),
            *(_tool_execution("Bash", success=False, event_sequence=i + 2, error_type="ShellError") for i in range(2)),
            filename="failure-rate-insights.jsonl",
        )
    )
    assert "Insights" in text
    assert "High tool failure rate" in text
    assert "- Bash: 2 failed of 4 calls (1/2)" in text
    assert "ShellError" not in text


def test_high_tool_failure_rate_not_present_below_min_calls() -> None:
    summary = _finish_tools(
        *(_tool_execution("Bash", success=False, event_sequence=i) for i in range(2)),
        filename="failure-rate-small.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "High tool failure rate" not in text
    assert parsed["insights"]["high_tool_failure_rate"] == []


def test_high_tool_failure_rate_not_present_below_rate_threshold() -> None:
    summary = _finish_tools(
        *(_tool_execution("Bash", success=True, event_sequence=i) for i in range(2)),
        _tool_execution("Bash", success=False, event_sequence=2),
        filename="failure-rate-below.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "High tool failure rate" not in text
    assert parsed["insights"]["high_tool_failure_rate"] == []


def test_high_tool_failure_rate_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                *(_tool_execution("Bash", success=True, event_sequence=i) for i in range(2)),
                *(_tool_execution("Bash", success=False, event_sequence=i + 2) for i in range(2)),
                filename="failure-rate-insights.jsonl",
            )
        )
    )
    assert parsed["insights"]["high_tool_failure_rate"] == [
        {
            "tool_name": "Bash",
            "failed_calls": 2,
            "total_calls": 4,
            "failure_rate": {"numerator": 1, "denominator": 2},
        }
    ]


def test_high_tool_failure_rate_above_boundaries_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                *(_tool_execution("Bash", success=True, event_sequence=i) for i in range(2)),
                *(_tool_execution("Bash", success=False, event_sequence=i + 2) for i in range(4)),
                filename="failure-rate-above.jsonl",
            )
        )
    )
    assert parsed["insights"]["high_tool_failure_rate"] == [
        {
            "tool_name": "Bash",
            "failed_calls": 4,
            "total_calls": 6,
            "failure_rate": {"numerator": 2, "denominator": 3},
        }
    ]


def test_high_tool_failure_rate_multiple_tools_ordered() -> None:
    records: list[ToolExecution] = []
    sequence = 0
    for tool_name, failures, calls in (("Zebra", 5, 5), ("Apple", 2, 4), ("Mango", 3, 3)):
        successes = calls - failures
        for _ in range(successes):
            records.append(_tool_execution(tool_name, success=True, event_sequence=sequence))
            sequence += 1
        for _ in range(failures):
            records.append(_tool_execution(tool_name, success=False, event_sequence=sequence))
            sequence += 1
    summary = _finish_tools(*records, filename="multi-failure-rate.jsonl")
    text = render_text(summary)
    payload = render_json(summary)
    assert "- Apple: 2 failed of 4 calls (1/2)" in text
    assert "- Mango: 3 failed of 3 calls (1/1)" in text
    assert "- Zebra: 5 failed of 5 calls (1/1)" in text
    apple_pos = text.index("- Apple: 2 failed of 4 calls (1/2)")
    mango_pos = text.index("- Mango: 3 failed of 3 calls (1/1)")
    zebra_pos = text.index("- Zebra: 5 failed of 5 calls (1/1)")
    assert apple_pos < mango_pos < zebra_pos
    parsed = json.loads(payload)
    assert [finding["tool_name"] for finding in parsed["insights"]["high_tool_failure_rate"]] == [
        "Apple",
        "Mango",
        "Zebra",
    ]
    assert parsed["insights"]["high_tool_failure_rate"][0]["failure_rate"] == {"numerator": 1, "denominator": 2}
    assert render_text(summary) == text
    assert render_json(summary) == payload


def test_high_tool_failure_rate_coexists_with_existing_insights() -> None:
    summary = _finish_tools(
        *(_tool_execution("Read", success=True, event_sequence=i, result_size_bytes=65536) for i in range(3)),
        *(
            _tool_execution(
                "Bash",
                success=False,
                event_sequence=i + 3,
                error_type="ShellError",
                result_size_bytes=0,
            )
            for i in range(4)
        ),
        *(_tool_execution("Bash", success=True, event_sequence=i + 7, result_size_bytes=0) for i in range(2)),
        filename="coexist-failure-rate.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "- Bash: 6 calls" in text
    assert "- Read: 3 calls" in text
    assert "- Bash: 4 failures" in text
    assert "- Read: 196608 result bytes" in text
    assert "- Bash: 4 failed of 6 calls (2/3)" in text
    assert parsed["insights"]["repeated_tool_calls"] == [
        {"tool_name": "Bash", "call_count": 6},
        {"tool_name": "Read", "call_count": 3},
    ]
    assert parsed["insights"]["repeated_failed_tool_calls"] == [{"tool_name": "Bash", "failure_count": 4}]
    assert parsed["insights"]["high_tool_result_volume"] == [{"tool_name": "Read", "result_bytes": 196608}]
    assert parsed["insights"]["high_tool_failure_rate"] == [
        {
            "tool_name": "Bash",
            "failed_calls": 4,
            "total_calls": 6,
            "failure_rate": {"numerator": 2, "denominator": 3},
        }
    ]


def test_high_tool_failure_rate_contains_only_safe_evidence() -> None:
    summary = _finish_tools(
        *(
            _tool_execution(
                "Bash",
                success=False,
                event_sequence=i,
                session_id="secret-session-id",
                prompt_id="secret-prompt-id",
                error_type="ShellError",
                tool_use_id="secret-tool-id",
            )
            for i in range(4)
        ),
        filename="failure-rate-privacy.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    _assert_markers_absent(
        text,
        payload,
        "secret-session-id",
        "secret-prompt-id",
        "secret-tool-id",
        "ShellError",
        "traceback",
        "rm -rf",
        "/tmp/",
        "arguments",
    )
    parsed = json.loads(payload)
    for finding in parsed["insights"]["high_tool_failure_rate"]:
        assert set(finding.keys()) == {"tool_name", "failed_calls", "total_calls", "failure_rate"}
        assert set(finding["failure_rate"].keys()) == {"numerator", "denominator"}
        assert isinstance(finding["failed_calls"], int)
        assert isinstance(finding["total_calls"], int)
        assert isinstance(finding["failure_rate"]["numerator"], int)
        assert isinstance(finding["failure_rate"]["denominator"], int)


def test_dominant_tool_appears_in_text() -> None:
    text = render_text(
        _finish_tools(
            *(_tool_execution("Read", success=True, event_sequence=i) for i in range(8)),
            *(_tool_execution("Grep", success=True, event_sequence=i + 8) for i in range(2)),
            filename="dominant-insights.jsonl",
        )
    )
    assert "Insights" in text
    assert "Dominant tool" in text
    assert "- Read: 8/10 calls (80%)" in text


def test_dominant_tool_not_present_below_minimum_sample() -> None:
    summary = _finish_tools(
        *(_tool_execution("Read", success=True, event_sequence=i) for i in range(9)),
        filename="dominant-below-sample.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Dominant tool" not in text
    assert parsed["insights"]["dominant_tool"] is None


def test_dominant_tool_not_present_below_share_threshold() -> None:
    summary = _finish_tools(
        *(_tool_execution("Read", success=True, event_sequence=i) for i in range(5)),
        *(_tool_execution("Grep", success=True, event_sequence=i + 5) for i in range(5)),
        filename="dominant-below-share.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Dominant tool" not in text
    assert parsed["insights"]["dominant_tool"] is None


def test_dominant_tool_at_threshold_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                *(_tool_execution("Read", success=True, event_sequence=i) for i in range(6)),
                *(_tool_execution("Grep", success=True, event_sequence=i + 6) for i in range(4)),
                filename="dominant-at-threshold.jsonl",
            )
        )
    )
    assert parsed["insights"]["dominant_tool"] == {
        "tool_name": "Read",
        "call_count": 6,
        "total_calls": 10,
        "share_percent": 60,
    }


def test_dominant_tool_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_tools(
                *(_tool_execution("Read", success=True, event_sequence=i) for i in range(8)),
                *(_tool_execution("Grep", success=True, event_sequence=i + 8) for i in range(2)),
                filename="dominant-insights.jsonl",
            )
        )
    )
    assert parsed["insights"]["dominant_tool"] == {
        "tool_name": "Read",
        "call_count": 8,
        "total_calls": 10,
        "share_percent": 80,
    }


def test_dominant_tool_text_and_json_are_deterministic() -> None:
    summary = _finish_tools(
        *(_tool_execution("Read", success=True, event_sequence=i) for i in range(8)),
        *(_tool_execution("Grep", success=True, event_sequence=i + 8) for i in range(2)),
        filename="dominant-deterministic.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    assert render_text(summary) == text
    assert render_json(summary) == payload
    parsed = json.loads(payload)
    assert "- Read: 8/10 calls (80%)" in text
    assert parsed["insights"]["dominant_tool"] == {
        "tool_name": "Read",
        "call_count": 8,
        "total_calls": 10,
        "share_percent": 80,
    }


def test_dominant_tool_coexists_with_existing_insights() -> None:
    summary = _finish_tools(
        *(_tool_execution("Read", success=True, event_sequence=i, result_size_bytes=24576) for i in range(8)),
        *(
            _tool_execution(
                "Bash",
                success=False,
                event_sequence=i + 8,
                error_type="ShellError",
                result_size_bytes=0,
            )
            for i in range(3)
        ),
        filename="dominant-coexist.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "- Read: 8 calls" in text
    assert "- Bash: 3 calls" in text
    assert "- Bash: 3 failures" in text
    assert "- Read: 196608 result bytes" in text
    assert "- Bash: 3 failed of 3 calls (1/1)" in text
    assert "- Read: 8/11 calls (72%)" in text
    assert parsed["insights"]["repeated_tool_calls"] == [
        {"tool_name": "Bash", "call_count": 3},
        {"tool_name": "Read", "call_count": 8},
    ]
    assert parsed["insights"]["repeated_failed_tool_calls"] == [{"tool_name": "Bash", "failure_count": 3}]
    assert parsed["insights"]["high_tool_result_volume"] == [{"tool_name": "Read", "result_bytes": 196608}]
    assert parsed["insights"]["high_tool_failure_rate"] == [
        {
            "tool_name": "Bash",
            "failed_calls": 3,
            "total_calls": 3,
            "failure_rate": {"numerator": 1, "denominator": 1},
        }
    ]
    assert parsed["insights"]["dominant_tool"] == {
        "tool_name": "Read",
        "call_count": 8,
        "total_calls": 11,
        "share_percent": 72,
    }


def test_dominant_tool_contains_only_safe_evidence() -> None:
    summary = _finish_tools(
        *(
            _tool_execution(
                "Read",
                success=True,
                event_sequence=i,
                session_id="secret-session-id",
                prompt_id="secret-prompt-id",
                tool_use_id="secret-tool-id",
            )
            for i in range(8)
        ),
        *(_tool_execution("Grep", success=True, event_sequence=i + 8) for i in range(2)),
        filename="dominant-privacy.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    _assert_markers_absent(
        text,
        payload,
        "secret-session-id",
        "secret-prompt-id",
        "secret-tool-id",
        "file contents",
        "/tmp/",
        "arguments",
        "should use Grep",
        "inefficient",
    )
    parsed = json.loads(payload)
    finding = parsed["insights"]["dominant_tool"]
    assert finding is not None
    assert set(finding.keys()) == {"tool_name", "call_count", "total_calls", "share_percent"}
    assert isinstance(finding["call_count"], int)
    assert isinstance(finding["total_calls"], int)
    assert isinstance(finding["share_percent"], int)


def test_compaction_pressure_appears_in_text() -> None:
    text = render_text(
        _finish_records(
            _compaction_event(1),
            _compaction_event(2),
            filename="compaction-insights.jsonl",
        )
    )
    assert "Insights" in text
    assert "Compaction pressure" in text
    assert "- 2 compactions" in text


def test_compaction_pressure_not_present_when_zero() -> None:
    summary = _finish_tools(
        _tool_execution("Read", success=True, event_sequence=1),
        filename="compaction-zero.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Compaction pressure" not in text
    assert parsed["insights"]["compaction_pressure"] is None


def test_compaction_pressure_not_present_below_threshold() -> None:
    summary = _finish_records(_compaction_event(1), filename="compaction-below.jsonl")
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Compaction pressure" not in text
    assert parsed["insights"]["compaction_pressure"] is None


def test_compaction_pressure_not_present_without_session_identifiers() -> None:
    summary = _finish_records(
        _compaction_event(1, session_id=None),
        _compaction_event(2, session_id=None),
        filename="compaction-no-session.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert summary.sessions.count == 0
    assert summary.sessions.compactions == 2
    assert "Compaction pressure" not in text
    assert parsed["insights"]["compaction_pressure"] is None


def test_compaction_pressure_at_threshold_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_records(
                _compaction_event(1),
                _compaction_event(2),
                filename="compaction-at-threshold.jsonl",
            )
        )
    )
    assert parsed["insights"]["compaction_pressure"] == {"compaction_count": 2}


def test_compaction_pressure_above_threshold_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_records(
                _compaction_event(1),
                _compaction_event(2),
                _compaction_event(3),
                filename="compaction-above.jsonl",
            )
        )
    )
    assert parsed["insights"]["compaction_pressure"] == {"compaction_count": 3}


def test_compaction_pressure_text_and_json_are_deterministic() -> None:
    summary = _finish_records(
        _compaction_event(1),
        _compaction_event(2),
        _compaction_event(3),
        filename="compaction-deterministic.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    assert render_text(summary) == text
    assert render_json(summary) == payload
    parsed = json.loads(payload)
    assert "- 3 compactions" in text
    assert parsed["insights"]["compaction_pressure"] == {"compaction_count": 3}


def test_compaction_pressure_coexists_with_existing_insights() -> None:
    summary = _finish_records(
        *(_tool_execution("Read", success=True, event_sequence=i, result_size_bytes=24576) for i in range(8)),
        *(
            _tool_execution(
                "Bash",
                success=False,
                event_sequence=i + 8,
                error_type="ShellError",
                result_size_bytes=0,
            )
            for i in range(3)
        ),
        _compaction_event(11),
        _compaction_event(12),
        filename="compaction-coexist.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "- Read: 8 calls" in text
    assert "- Bash: 3 calls" in text
    assert "- Bash: 3 failures" in text
    assert "- Read: 196608 result bytes" in text
    assert "- Bash: 3 failed of 3 calls (1/1)" in text
    assert "- Read: 8/11 calls (72%)" in text
    assert "- 2 compactions" in text
    assert parsed["insights"]["repeated_tool_calls"] == [
        {"tool_name": "Bash", "call_count": 3},
        {"tool_name": "Read", "call_count": 8},
    ]
    assert parsed["insights"]["repeated_failed_tool_calls"] == [{"tool_name": "Bash", "failure_count": 3}]
    assert parsed["insights"]["high_tool_result_volume"] == [{"tool_name": "Read", "result_bytes": 196608}]
    assert parsed["insights"]["high_tool_failure_rate"] == [
        {
            "tool_name": "Bash",
            "failed_calls": 3,
            "total_calls": 3,
            "failure_rate": {"numerator": 1, "denominator": 1},
        }
    ]
    assert parsed["insights"]["dominant_tool"] == {
        "tool_name": "Read",
        "call_count": 8,
        "total_calls": 11,
        "share_percent": 72,
    }
    assert parsed["insights"]["compaction_pressure"] == {"compaction_count": 2}
    assert parsed["insights"]["subagent_usage"] is None


def test_compaction_pressure_contains_only_safe_evidence() -> None:
    summary = _finish_records(
        _compaction_event(1, session_id="secret-session-id"),
        _compaction_event(2, session_id="secret-session-id"),
        filename="compaction-privacy.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    _assert_markers_absent(
        text,
        payload,
        "secret-session-id",
        "secret-prompt-id",
        "/tmp/",
        "context window",
        "should compact less",
        "degraded",
        "recommend",
    )
    parsed = json.loads(payload)
    finding = parsed["insights"]["compaction_pressure"]
    assert finding is not None
    assert set(finding.keys()) == {"compaction_count"}
    assert isinstance(finding["compaction_count"], int)


def test_subagent_usage_appears_in_text() -> None:
    text = render_text(
        _finish_records(
            _subagent_event(1),
            _subagent_event(2),
            filename="subagent-insights.jsonl",
        )
    )
    assert "Insights" in text
    assert "Subagent usage" in text
    assert "- 2 completed" in text


def test_subagent_usage_not_present_when_zero() -> None:
    summary = _finish_tools(
        _tool_execution("Read", success=True, event_sequence=1),
        filename="subagent-zero.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Subagent usage" not in text
    assert parsed["insights"]["subagent_usage"] is None


def test_subagent_usage_not_present_below_threshold() -> None:
    summary = _finish_records(_subagent_event(1), filename="subagent-below.jsonl")
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "Subagent usage" not in text
    assert parsed["insights"]["subagent_usage"] is None


def test_subagent_usage_at_threshold_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_records(
                _subagent_event(1),
                _subagent_event(2),
                filename="subagent-at-threshold.jsonl",
            )
        )
    )
    assert parsed["insights"]["subagent_usage"] == {"completed_count": 2}


def test_subagent_usage_above_threshold_in_json_output() -> None:
    parsed = json.loads(
        render_json(
            _finish_records(
                _subagent_event(1),
                _subagent_event(2),
                _subagent_event(3),
                filename="subagent-above.jsonl",
            )
        )
    )
    assert parsed["insights"]["subagent_usage"] == {"completed_count": 3}


def test_subagent_usage_text_and_json_are_deterministic() -> None:
    summary = _finish_records(
        _subagent_event(1),
        _subagent_event(2),
        _subagent_event(3),
        filename="subagent-deterministic.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    assert render_text(summary) == text
    assert render_json(summary) == payload
    parsed = json.loads(payload)
    assert "- 3 completed" in text
    assert parsed["insights"]["subagent_usage"] == {"completed_count": 3}


def test_subagent_usage_coexists_with_existing_insights() -> None:
    summary = _finish_records(
        *(_tool_execution("Read", success=True, event_sequence=i, result_size_bytes=24576) for i in range(8)),
        *(
            _tool_execution(
                "Bash",
                success=False,
                event_sequence=i + 8,
                error_type="ShellError",
                result_size_bytes=0,
            )
            for i in range(3)
        ),
        _compaction_event(11),
        _compaction_event(12),
        _subagent_event(13),
        _subagent_event(14),
        filename="subagent-coexist.jsonl",
    )
    text = render_text(summary)
    parsed = json.loads(render_json(summary))
    assert "- Read: 8 calls" in text
    assert "- Bash: 3 calls" in text
    assert "- Bash: 3 failures" in text
    assert "- Read: 196608 result bytes" in text
    assert "- Bash: 3 failed of 3 calls (1/1)" in text
    assert "- Read: 8/11 calls (72%)" in text
    assert "- 2 compactions" in text
    assert "- 2 completed" in text
    assert text.index("Compaction pressure") < text.index("Subagent usage")
    assert parsed["insights"]["repeated_tool_calls"] == [
        {"tool_name": "Bash", "call_count": 3},
        {"tool_name": "Read", "call_count": 8},
    ]
    assert parsed["insights"]["repeated_failed_tool_calls"] == [{"tool_name": "Bash", "failure_count": 3}]
    assert parsed["insights"]["high_tool_result_volume"] == [{"tool_name": "Read", "result_bytes": 196608}]
    assert parsed["insights"]["high_tool_failure_rate"] == [
        {
            "tool_name": "Bash",
            "failed_calls": 3,
            "total_calls": 3,
            "failure_rate": {"numerator": 1, "denominator": 1},
        }
    ]
    assert parsed["insights"]["dominant_tool"] == {
        "tool_name": "Read",
        "call_count": 8,
        "total_calls": 11,
        "share_percent": 72,
    }
    assert parsed["insights"]["compaction_pressure"] == {"compaction_count": 2}
    assert parsed["insights"]["subagent_usage"] == {"completed_count": 2}


def test_subagent_usage_contains_only_safe_evidence() -> None:
    summary = _finish_records(
        _subagent_event(1, session_id="secret-session-id"),
        _subagent_event(2, session_id="secret-session-id"),
        filename="subagent-privacy.jsonl",
    )
    text = render_text(summary)
    payload = render_json(summary)
    _assert_markers_absent(
        text,
        payload,
        "secret-session-id",
        "secret-prompt-id",
        "/tmp/",
        "researcher",
        "should delegate",
        "wasteful",
        "helpful",
        "recommend",
    )
    parsed = json.loads(payload)
    finding = parsed["insights"]["subagent_usage"]
    assert finding is not None
    assert set(finding.keys()) == {"completed_count"}
    assert isinstance(finding["completed_count"], int)
