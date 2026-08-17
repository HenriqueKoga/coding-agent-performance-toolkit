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
