from datetime import datetime
from pathlib import Path

from coding_agent_performance.trace.accumulators import duration_stats, nearest_rank
from coding_agent_performance.trace.aggregation import IncrementalSummarizer
from coding_agent_performance.trace.capture import CaptureEnvelope
from coding_agent_performance.trace.records import (
    ActivityMeasurement,
    AggregationTemporality,
    MetricAttributes,
    MetricKind,
    ModelRequest,
    NamedLifecycleEvent,
    ToolExecution,
)
from tests.helpers.otlp import resource_logs, resource_metrics


def _envelope(
    signal: str, payload: dict[str, object], received_at: str = "2026-08-15T10:00:00+00:00"
) -> CaptureEnvelope:
    return CaptureEnvelope(
        schema_version=1,
        received_at=datetime.fromisoformat(received_at),
        source="claude-code",
        signal=signal,
        payload=payload,
    )


def _measurement(
    name: str,
    value: int | float,
    *,
    attributes: MetricAttributes = (),
    start_time_unix_nano: int | None = 1,
    time_unix_nano: int | None = None,
    aggregation_temporality: AggregationTemporality | None = None,
    kind: MetricKind = "sum",
) -> ActivityMeasurement:
    return ActivityMeasurement(
        name=name,
        value=value,
        unit="",
        attributes=attributes,
        start_time_unix_nano=start_time_unix_nano,
        time_unix_nano=time_unix_nano,
        aggregation_temporality=aggregation_temporality,
        kind=kind,
    )


def test_delta_metrics_are_summed() -> None:
    summarizer = IncrementalSummarizer(filename="delta.jsonl")
    first = _measurement("claude_code.commit.count", 2, time_unix_nano=10, aggregation_temporality="delta")
    second = _measurement("claude_code.commit.count", 3, time_unix_nano=20, aggregation_temporality="delta")
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (first, second), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("delta.jsonl")).activity.commits == 5


def test_cumulative_uses_latest_timestamp_not_max_value() -> None:
    summarizer = IncrementalSummarizer(filename="cum.jsonl")
    older = _measurement("claude_code.commit.count", 9, time_unix_nano=10, aggregation_temporality="cumulative")
    newer = _measurement("claude_code.commit.count", 3, time_unix_nano=20, aggregation_temporality="cumulative")
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (older, newer), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("cum.jsonl")).activity.commits == 3


def test_counter_reset_uses_start_time_identity() -> None:
    summarizer = IncrementalSummarizer(filename="reset.jsonl")
    first = _measurement("claude_code.commit.count", 4, time_unix_nano=10, aggregation_temporality="cumulative")
    reset = _measurement(
        "claude_code.commit.count",
        2,
        start_time_unix_nano=99,
        time_unix_nano=20,
        aggregation_temporality="cumulative",
    )
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (first, reset), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("reset.jsonl")).activity.commits == 6


def test_missing_temporality_uses_latest_and_warns() -> None:
    summarizer = IncrementalSummarizer(filename="tmp.jsonl")
    first = _measurement("claude_code.commit.count", 1, time_unix_nano=10)
    second = _measurement("claude_code.commit.count", 8, time_unix_nano=20)
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
        _measurement(
            "claude_code.lines_of_code.count",
            3,
            attributes=(("type", "added"),),
            aggregation_temporality="delta",
        ),
        _measurement("claude_code.pull_request.count", 1, time_unix_nano=5, aggregation_temporality="delta"),
        _measurement(
            "claude_code.code_edit_tool.decision",
            2,
            attributes=(("decision", "reject"),),
            time_unix_nano=6,
            aggregation_temporality="delta",
        ),
        _measurement("claude_code.commit.count", 1, time_unix_nano=1, aggregation_temporality="cumulative"),
        _measurement("claude_code.commit.count", 9, time_unix_nano=0, aggregation_temporality="cumulative"),
    )
    summarizer.add(_envelope("logs", resource_logs([])), records, log_count=6, metric_count=5, unsupported=0)
    summary = summarizer.finish(Path("life.jsonl"))
    assert summary.model_usage.refusals == 1
    assert summary.sessions.compactions == 1
    assert summary.sessions.subagents_completed == 1
    assert summary.activity.lines_of_code.added == 3
    assert summary.activity.pull_requests == 1
    assert summary.activity.code_edit_decisions.rejected == 2
    assert summary.activity.commits == 1


def test_known_timestamp_wins_over_missing_when_known_is_first() -> None:
    summarizer = IncrementalSummarizer(filename="ts.jsonl")
    known = _measurement("claude_code.commit.count", 3, time_unix_nano=10, aggregation_temporality="cumulative")
    missing = _measurement("claude_code.commit.count", 99, aggregation_temporality="cumulative")
    summarizer.add(
        _envelope("metrics", resource_metrics([])), (known, missing), log_count=0, metric_count=2, unsupported=0
    )
    assert summarizer.finish(Path("ts.jsonl")).activity.commits == 3


def test_known_timestamp_wins_over_missing_when_missing_is_first() -> None:
    summarizer = IncrementalSummarizer(filename="ts.jsonl")
    missing = _measurement("claude_code.commit.count", 99, aggregation_temporality="cumulative")
    known = _measurement("claude_code.commit.count", 3, time_unix_nano=10, aggregation_temporality="cumulative")
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


def test_unknown_otlp_values_are_accumulated() -> None:
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
    assert summarizer.finish(Path("unknown.jsonl")).coverage.unknown_otlp_values == 5
