import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from coding_agent_performance.trace.aggregation import IncrementalSummarizer
from coding_agent_performance.trace.capture import CaptureEnvelope
from coding_agent_performance.trace.records import ToolExecution
from coding_agent_performance.trace.rendering import (
    escape_filename,
    format_utc_timestamp,
    render_capture_list,
    render_capture_listing,
    render_json,
    render_text,
    summary_to_dict,
)
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
    summarizer = IncrementalSummarizer(filename="insights.jsonl")
    for _ in range(5):
        tool = ToolExecution(
            session_id=None,
            prompt_id=None,
            tool_name="Read",
            success=True,
            duration_ms=10,
            input_size_bytes=100,
            result_size_bytes=200,
            error_type=None,
            tool_use_id=None,
            event_sequence=1,
        )
        summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    text = render_text(summarizer.finish(Path("insights.jsonl")))
    assert "Insights" in text
    assert "Repeated tool calls" in text
    assert "- Read: 5 calls" in text


def test_insights_not_present_when_no_findings() -> None:
    summarizer = IncrementalSummarizer(filename="no-insights.jsonl")
    tool = ToolExecution(
        session_id=None,
        prompt_id=None,
        tool_name="Read",
        success=True,
        duration_ms=10,
        input_size_bytes=100,
        result_size_bytes=200,
        error_type=None,
        tool_use_id=None,
        event_sequence=1,
    )
    summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    text = render_text(summarizer.finish(Path("no-insights.jsonl")))
    assert "Insights" not in text


def test_insights_in_json_output() -> None:
    summarizer = IncrementalSummarizer(filename="insights.jsonl")
    for i in range(8):
        tool = ToolExecution(
            session_id=None,
            prompt_id=None,
            tool_name="Read",
            success=True,
            duration_ms=10,
            input_size_bytes=100,
            result_size_bytes=200,
            error_type=None,
            tool_use_id=None,
            event_sequence=i,
        )
        summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    summary = summarizer.finish(Path("insights.jsonl"))
    parsed = json.loads(render_json(summary))
    assert "insights" in parsed
    assert "repeated_tool_calls" in parsed["insights"]
    findings = parsed["insights"]["repeated_tool_calls"]
    assert len(findings) == 1
    assert findings[0]["tool_name"] == "Read"
    assert findings[0]["call_count"] == 8


def test_insights_multiple_repeated_tools_ordered() -> None:
    summarizer = IncrementalSummarizer(filename="multi-insights.jsonl")
    tools_data = [("Zebra", 5), ("Apple", 4), ("Mango", 3)]
    for tool_name, count in tools_data:
        for i in range(count):
            tool = ToolExecution(
                session_id=None,
                prompt_id=None,
                tool_name=tool_name,
                success=True,
                duration_ms=10,
                input_size_bytes=100,
                result_size_bytes=200,
                error_type=None,
                tool_use_id=None,
                event_sequence=i,
            )
            summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    text = render_text(summarizer.finish(Path("multi-insights.jsonl")))
    assert "- Apple: 4 calls" in text
    assert "- Mango: 3 calls" in text
    assert "- Zebra: 5 calls" in text
    apple_pos = text.index("- Apple: 4 calls")
    mango_pos = text.index("- Mango: 3 calls")
    zebra_pos = text.index("- Zebra: 5 calls")
    assert apple_pos < mango_pos < zebra_pos


def test_insights_contain_only_safe_evidence() -> None:
    summarizer = IncrementalSummarizer(filename="privacy.jsonl")
    for i in range(5):
        tool = ToolExecution(
            session_id="secret-session-id",
            prompt_id="secret-prompt-id",
            tool_name="Read",
            success=True,
            duration_ms=10,
            input_size_bytes=100,
            result_size_bytes=200,
            error_type=None,
            tool_use_id="secret-tool-id",
            event_sequence=i,
        )
        summarizer.add(_envelope("logs", resource_logs([])), (tool,), log_count=1, metric_count=0, unsupported=0)
    summary = summarizer.finish(Path("privacy.jsonl"))
    text = render_text(summary)
    payload = render_json(summary)
    assert "secret-session-id" not in text
    assert "secret-prompt-id" not in text
    assert "secret-tool-id" not in text
    assert "secret-session-id" not in payload
    assert "secret-prompt-id" not in payload
    assert "secret-tool-id" not in payload
    parsed = json.loads(payload)
    for finding in parsed["insights"]["repeated_tool_calls"]:
        assert set(finding.keys()) == {"tool_name", "call_count"}
