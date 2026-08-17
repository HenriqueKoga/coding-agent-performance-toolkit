"""Tests for deterministic insight rules."""

from coding_agent_performance.trace.insights import (
    compute_insights,
    detect_repeated_failed_tool_calls,
    detect_repeated_tool_calls,
)
from coding_agent_performance.trace.report import (
    DurationStats,
    Insights,
    RepeatedFailedToolCall,
    RepeatedToolCall,
    ToolBreakdown,
    ToolStats,
)


def test_detect_repeated_tool_calls_no_tools() -> None:
    tools = ToolStats(
        calls=0,
        successes=0,
        failures=0,
        input_bytes=0,
        result_bytes=0,
        duration_ms=DurationStats(total=0, average=None, p50=None, p95=None),
        by_name=(),
    )
    findings = detect_repeated_tool_calls(tools)
    assert findings == ()


def test_detect_repeated_tool_calls_below_threshold() -> None:
    tools = ToolStats(
        calls=2,
        successes=2,
        failures=0,
        input_bytes=0,
        result_bytes=0,
        duration_ms=DurationStats(total=0, average=None, p50=None, p95=None),
        by_name=(
            ToolBreakdown(
                name="Read",
                calls=2,
                successes=2,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
        ),
    )
    findings = detect_repeated_tool_calls(tools)
    assert findings == ()


def test_detect_repeated_tool_calls_at_threshold() -> None:
    tools = ToolStats(
        calls=3,
        successes=3,
        failures=0,
        input_bytes=0,
        result_bytes=0,
        duration_ms=DurationStats(total=0, average=None, p50=None, p95=None),
        by_name=(
            ToolBreakdown(
                name="Read",
                calls=3,
                successes=3,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
        ),
    )
    findings = detect_repeated_tool_calls(tools)
    assert findings == (RepeatedToolCall(tool_name="Read", call_count=3),)


def test_detect_repeated_tool_calls_above_threshold() -> None:
    tools = ToolStats(
        calls=8,
        successes=8,
        failures=0,
        input_bytes=0,
        result_bytes=0,
        duration_ms=DurationStats(total=0, average=None, p50=None, p95=None),
        by_name=(
            ToolBreakdown(
                name="Read",
                calls=8,
                successes=8,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
        ),
    )
    findings = detect_repeated_tool_calls(tools)
    assert findings == (RepeatedToolCall(tool_name="Read", call_count=8),)


def test_detect_repeated_tool_calls_multiple_tools() -> None:
    tools = ToolStats(
        calls=15,
        successes=15,
        failures=0,
        input_bytes=0,
        result_bytes=0,
        duration_ms=DurationStats(total=0, average=None, p50=None, p95=None),
        by_name=(
            ToolBreakdown(
                name="Read",
                calls=8,
                successes=8,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
            ToolBreakdown(
                name="Grep",
                calls=5,
                successes=5,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
            ToolBreakdown(
                name="Write",
                calls=2,
                successes=2,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
        ),
    )
    findings = detect_repeated_tool_calls(tools)
    assert findings == (
        RepeatedToolCall(tool_name="Grep", call_count=5),
        RepeatedToolCall(tool_name="Read", call_count=8),
    )


def test_detect_repeated_tool_calls_deterministic_ordering() -> None:
    tools = ToolStats(
        calls=13,
        successes=13,
        failures=0,
        input_bytes=0,
        result_bytes=0,
        duration_ms=DurationStats(total=0, average=None, p50=None, p95=None),
        by_name=(
            ToolBreakdown(
                name="Zebra",
                calls=5,
                successes=5,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
            ToolBreakdown(
                name="Apple",
                calls=4,
                successes=4,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
            ToolBreakdown(
                name="Mango",
                calls=4,
                successes=4,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
        ),
    )
    findings = detect_repeated_tool_calls(tools)
    assert findings == (
        RepeatedToolCall(tool_name="Apple", call_count=4),
        RepeatedToolCall(tool_name="Mango", call_count=4),
        RepeatedToolCall(tool_name="Zebra", call_count=5),
    )


def test_compute_insights() -> None:
    tools = ToolStats(
        calls=8,
        successes=8,
        failures=0,
        input_bytes=0,
        result_bytes=0,
        duration_ms=DurationStats(total=0, average=None, p50=None, p95=None),
        by_name=(
            ToolBreakdown(
                name="Read",
                calls=8,
                successes=8,
                failures=0,
                success_rate=1.0,
                duration_ms_total=0,
                duration_ms_average=None,
                input_bytes=0,
                result_bytes=0,
            ),
        ),
    )
    insights = compute_insights(tools)
    assert isinstance(insights, Insights)
    assert insights.repeated_tool_calls == (RepeatedToolCall(tool_name="Read", call_count=8),)
    assert insights.repeated_failed_tool_calls == ()


def test_repeated_tool_call_contains_only_safe_evidence() -> None:
    finding = RepeatedToolCall(tool_name="Read", call_count=10)
    assert hasattr(finding, "tool_name")
    assert hasattr(finding, "call_count")
    assert not hasattr(finding, "arguments")
    assert not hasattr(finding, "result")
    assert not hasattr(finding, "input")
    assert not hasattr(finding, "output")


def _empty_duration() -> DurationStats:
    return DurationStats(total=0, average=None, p50=None, p95=None)


def _tool(
    name: str,
    *,
    calls: int,
    successes: int | None = None,
    failures: int = 0,
) -> ToolBreakdown:
    resolved_successes = calls - failures if successes is None else successes
    return ToolBreakdown(
        name=name,
        calls=calls,
        successes=resolved_successes,
        failures=failures,
        success_rate=(resolved_successes / calls) if calls else None,
        duration_ms_total=0,
        duration_ms_average=None,
        input_bytes=0,
        result_bytes=0,
    )


def _tools(*rows: ToolBreakdown) -> ToolStats:
    return ToolStats(
        calls=sum(row.calls for row in rows),
        successes=sum(row.successes for row in rows),
        failures=sum(row.failures for row in rows),
        input_bytes=0,
        result_bytes=0,
        duration_ms=_empty_duration(),
        by_name=rows,
    )


def test_detect_repeated_failed_tool_calls_no_failures() -> None:
    findings = detect_repeated_failed_tool_calls(_tools())
    assert findings == ()


def test_detect_repeated_failed_tool_calls_successful_calls_only() -> None:
    findings = detect_repeated_failed_tool_calls(_tools(_tool("Bash", calls=8, failures=0)))
    assert findings == ()


def test_detect_repeated_failed_tool_calls_below_threshold() -> None:
    findings = detect_repeated_failed_tool_calls(_tools(_tool("Bash", calls=2, failures=2)))
    assert findings == ()


def test_detect_repeated_failed_tool_calls_at_threshold() -> None:
    findings = detect_repeated_failed_tool_calls(_tools(_tool("Bash", calls=3, failures=3)))
    assert findings == (RepeatedFailedToolCall(tool_name="Bash", failure_count=3),)


def test_detect_repeated_failed_tool_calls_above_threshold() -> None:
    findings = detect_repeated_failed_tool_calls(_tools(_tool("Bash", calls=8, failures=8)))
    assert findings == (RepeatedFailedToolCall(tool_name="Bash", failure_count=8),)


def test_detect_repeated_failed_tool_calls_mixed_success_and_failure() -> None:
    findings = detect_repeated_failed_tool_calls(_tools(_tool("Bash", calls=7, successes=4, failures=3)))
    assert findings == (RepeatedFailedToolCall(tool_name="Bash", failure_count=3),)


def test_detect_repeated_failed_tool_calls_mixed_below_threshold() -> None:
    findings = detect_repeated_failed_tool_calls(_tools(_tool("Bash", calls=12, successes=10, failures=2)))
    assert findings == ()


def test_detect_repeated_failed_tool_calls_multiple_tools() -> None:
    findings = detect_repeated_failed_tool_calls(
        _tools(
            _tool("Read", calls=8, failures=8),
            _tool("Grep", calls=5, failures=5),
            _tool("Write", calls=2, failures=2),
        )
    )
    assert findings == (
        RepeatedFailedToolCall(tool_name="Grep", failure_count=5),
        RepeatedFailedToolCall(tool_name="Read", failure_count=8),
    )


def test_detect_repeated_failed_tool_calls_deterministic_ordering() -> None:
    findings = detect_repeated_failed_tool_calls(
        _tools(
            _tool("Zebra", calls=5, failures=5),
            _tool("Apple", calls=4, failures=4),
            _tool("Mango", calls=4, failures=4),
        )
    )
    assert findings == (
        RepeatedFailedToolCall(tool_name="Apple", failure_count=4),
        RepeatedFailedToolCall(tool_name="Mango", failure_count=4),
        RepeatedFailedToolCall(tool_name="Zebra", failure_count=5),
    )


def test_compute_insights_keeps_repeated_calls_independent_of_failures() -> None:
    insights = compute_insights(
        _tools(
            _tool("Read", calls=8, successes=8, failures=0),
            _tool("Bash", calls=7, successes=4, failures=3),
        )
    )
    assert insights.repeated_tool_calls == (
        RepeatedToolCall(tool_name="Bash", call_count=7),
        RepeatedToolCall(tool_name="Read", call_count=8),
    )
    assert insights.repeated_failed_tool_calls == (RepeatedFailedToolCall(tool_name="Bash", failure_count=3),)


def test_repeated_failed_tool_call_contains_only_safe_evidence() -> None:
    finding = RepeatedFailedToolCall(tool_name="Bash", failure_count=4)
    assert hasattr(finding, "tool_name")
    assert hasattr(finding, "failure_count")
    assert not hasattr(finding, "arguments")
    assert not hasattr(finding, "result")
    assert not hasattr(finding, "error")
    assert not hasattr(finding, "error_type")
    assert not hasattr(finding, "input")
    assert not hasattr(finding, "output")
    assert not hasattr(finding, "payload")
