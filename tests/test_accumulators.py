import ast
from datetime import datetime
from pathlib import Path

from coding_agent_performance.trace.accumulators import (
    CaptureAccumulator,
    CoverageAccumulator,
    MetricAccumulator,
    SessionAccumulator,
    ToolAccumulator,
    UsageAccumulator,
)
from coding_agent_performance.trace.capture import CaptureEnvelope
from coding_agent_performance.trace.records import ActivityMeasurement, ModelRequest, ToolExecution
from tests.helpers.otlp import resource_logs

_TRACE_DIR = Path("src/coding_agent_performance/trace")
_FORBIDDEN_PREFIXES = (
    "coding_agent_performance.adapters",
    "coding_agent_performance.cli",
    "coding_agent_performance.trace.cli",
    "coding_agent_performance.trace.rendering",
)
_FORBIDDEN_MODULES = frozenset({"typer"})


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _assert_core_imports_are_provider_neutral(path: Path) -> None:
    imported = _imported_modules(path)
    assert imported.isdisjoint(_FORBIDDEN_MODULES)
    for name in imported:
        assert all(not name.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)


def test_accumulator_and_analyzer_modules_stay_provider_neutral() -> None:
    _assert_core_imports_are_provider_neutral(_TRACE_DIR / "accumulators.py")
    _assert_core_imports_are_provider_neutral(_TRACE_DIR / "insights.py")
    _assert_core_imports_are_provider_neutral(_TRACE_DIR / "aggregation.py")
    _assert_core_imports_are_provider_neutral(_TRACE_DIR / "comparison.py")


def test_tool_accumulator_snapshots_immutable_stats() -> None:
    tools = ToolAccumulator()
    tools.add(
        ToolExecution(
            session_id="session-a",
            prompt_id="prompt-a",
            tool_name="Read",
            success=True,
            duration_ms=400,
            input_size_bytes=10,
            result_size_bytes=20,
            error_type=None,
            tool_use_id="tool-1",
            event_sequence=1,
        )
    )
    tools.add(
        ToolExecution(
            session_id="session-a",
            prompt_id="prompt-a",
            tool_name="Bash",
            success=False,
            duration_ms=None,
            input_size_bytes=None,
            result_size_bytes=5,
            error_type="exit",
            tool_use_id="tool-2",
            event_sequence=2,
        )
    )
    snapshot = tools.snapshot()
    assert snapshot.calls == 2
    assert snapshot.successes == 1
    assert snapshot.failures == 1
    assert snapshot.input_bytes == 10
    assert snapshot.result_bytes == 25
    assert [row.name for row in snapshot.by_name] == ["Bash", "Read"]
    assert snapshot.by_name[1].duration_ms_average == 400.0
    assert snapshot.by_name[0].duration_ms_average is None
    assert not hasattr(snapshot, "arguments")
    assert not hasattr(snapshot.by_name[0], "error_type")


def test_session_accumulator_prefers_observed_ids() -> None:
    sessions = SessionAccumulator()
    sessions.add_id("session-a")
    sessions.add_prompt()
    assert sessions.snapshot(metric_session_count=9).count == 1
    empty = SessionAccumulator()
    assert empty.snapshot(metric_session_count=9).count == 9


def test_coverage_accumulator_deduplicates_log_identities() -> None:
    coverage = CoverageAccumulator()
    identity = ("session-a", 1, "api_request")
    assert coverage.observe_log(identity) is True
    assert coverage.observe_log(identity) is False
    snapshot = coverage.snapshot()
    assert snapshot.duplicate_log_records == 1


def test_usage_accumulator_prefers_events_over_metrics() -> None:
    usage = UsageAccumulator()
    usage.add_request(
        ModelRequest(
            session_id="session-a",
            prompt_id="prompt-a",
            model="claude-example",
            query_source="main",
            duration_ms=10,
            input_tokens=3,
            output_tokens=1,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            estimated_cost_usd_micros=7,
            event_sequence=1,
        )
    )
    metrics = MetricAccumulator()
    metrics.add(
        ActivityMeasurement(
            name="claude_code.token.usage",
            value=99,
            unit="tokens",
            attributes=(("type", "input"),),
            start_time_unix_nano=1,
            time_unix_nano=1,
            aggregation_temporality="delta",
            kind="sum",
        )
    )
    snapshot = usage.snapshot(metrics)
    assert snapshot.usage_source == "api_request_events"
    assert snapshot.tokens.input == 3
    assert snapshot.estimated_cost_usd_micros == 7


def test_capture_accumulator_tracks_batch_bounds() -> None:
    capture = CaptureAccumulator(filename="session.jsonl")
    first = CaptureEnvelope(
        schema_version=1,
        received_at=datetime.fromisoformat("2026-08-15T10:00:00+00:00"),
        source="claude-code",
        signal="logs",
        payload=resource_logs([]),
    )
    second = CaptureEnvelope(
        schema_version=1,
        received_at=datetime.fromisoformat("2026-08-15T10:01:00+00:00"),
        source="claude-code",
        signal="metrics",
        payload={"resourceMetrics": []},
    )
    capture.add(first)
    capture.add(second)
    snapshot = capture.snapshot()
    assert snapshot.file == "session.jsonl"
    assert snapshot.envelopes == 2
    assert snapshot.log_batches == 1
    assert snapshot.metric_batches == 1
    assert snapshot.first_received_at == "2026-08-15T10:00:00+00:00"
    assert snapshot.last_received_at == "2026-08-15T10:01:00+00:00"
    assert "/" not in snapshot.file
