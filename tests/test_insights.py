"""Tests for deterministic insight rules."""

from coding_agent_performance.trace.insights import compute_insights, detect_repeated_tool_calls
from coding_agent_performance.trace.report import (
    DurationStats,
    Insights,
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


def test_repeated_tool_call_contains_only_safe_evidence() -> None:
    finding = RepeatedToolCall(tool_name="Read", call_count=10)
    assert hasattr(finding, "tool_name")
    assert hasattr(finding, "call_count")
    assert not hasattr(finding, "arguments")
    assert not hasattr(finding, "result")
    assert not hasattr(finding, "input")
    assert not hasattr(finding, "output")
