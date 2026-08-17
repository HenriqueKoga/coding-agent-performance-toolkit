"""Tests for deterministic insight rules."""

from math import gcd

from coding_agent_performance.trace.insights import (
    HIGH_TOOL_RESULT_VOLUME_THRESHOLD,
    compute_insights,
    detect_high_tool_failure_rate,
    detect_high_tool_result_volume,
    detect_repeated_failed_tool_calls,
    detect_repeated_tool_calls,
)
from coding_agent_performance.trace.report import (
    DurationStats,
    FailureRate,
    HighToolFailureRate,
    HighToolResultVolume,
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
    assert insights.high_tool_result_volume == ()
    assert insights.high_tool_failure_rate == ()


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
    result_bytes: int = 0,
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
        result_bytes=result_bytes,
    )


def _tools(*rows: ToolBreakdown) -> ToolStats:
    return ToolStats(
        calls=sum(row.calls for row in rows),
        successes=sum(row.successes for row in rows),
        failures=sum(row.failures for row in rows),
        input_bytes=0,
        result_bytes=sum(row.result_bytes for row in rows),
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
    assert insights.high_tool_result_volume == ()
    assert insights.high_tool_failure_rate == ()


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


def test_detect_high_tool_result_volume_no_tools() -> None:
    findings = detect_high_tool_result_volume(_tools())
    assert findings == ()


def test_detect_high_tool_result_volume_zero_result_bytes() -> None:
    findings = detect_high_tool_result_volume(_tools(_tool("Read", calls=1, result_bytes=0)))
    assert findings == ()


def test_detect_high_tool_result_volume_below_threshold() -> None:
    findings = detect_high_tool_result_volume(
        _tools(_tool("Read", calls=1, result_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD - 1))
    )
    assert findings == ()


def test_detect_high_tool_result_volume_at_threshold() -> None:
    findings = detect_high_tool_result_volume(
        _tools(_tool("Read", calls=1, result_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD))
    )
    assert findings == (HighToolResultVolume(tool_name="Read", result_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD),)


def test_detect_high_tool_result_volume_above_threshold() -> None:
    findings = detect_high_tool_result_volume(_tools(_tool("Read", calls=1, result_bytes=196608)))
    assert findings == (HighToolResultVolume(tool_name="Read", result_bytes=196608),)


def test_detect_high_tool_result_volume_multiple_tools() -> None:
    findings = detect_high_tool_result_volume(
        _tools(
            _tool("Read", calls=1, result_bytes=196608),
            _tool("Grep", calls=1, result_bytes=147456),
            _tool("Write", calls=1, result_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD - 1),
        )
    )
    assert findings == (
        HighToolResultVolume(tool_name="Grep", result_bytes=147456),
        HighToolResultVolume(tool_name="Read", result_bytes=196608),
    )


def test_detect_high_tool_result_volume_deterministic_ordering() -> None:
    findings = detect_high_tool_result_volume(
        _tools(
            _tool("Zebra", calls=1, result_bytes=196608),
            _tool("Apple", calls=1, result_bytes=147456),
            _tool("Mango", calls=1, result_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD),
        )
    )
    assert findings == (
        HighToolResultVolume(tool_name="Apple", result_bytes=147456),
        HighToolResultVolume(tool_name="Mango", result_bytes=HIGH_TOOL_RESULT_VOLUME_THRESHOLD),
        HighToolResultVolume(tool_name="Zebra", result_bytes=196608),
    )


def test_compute_insights_keeps_existing_rules_independent_of_result_volume() -> None:
    insights = compute_insights(
        _tools(
            _tool("Read", calls=8, successes=8, failures=0, result_bytes=196608),
            _tool("Bash", calls=7, successes=4, failures=3, result_bytes=0),
            _tool("Grep", calls=1, result_bytes=147456),
        )
    )
    assert insights.repeated_tool_calls == (
        RepeatedToolCall(tool_name="Bash", call_count=7),
        RepeatedToolCall(tool_name="Read", call_count=8),
    )
    assert insights.repeated_failed_tool_calls == (RepeatedFailedToolCall(tool_name="Bash", failure_count=3),)
    assert insights.high_tool_result_volume == (
        HighToolResultVolume(tool_name="Grep", result_bytes=147456),
        HighToolResultVolume(tool_name="Read", result_bytes=196608),
    )
    assert insights.high_tool_failure_rate == ()


def test_high_tool_result_volume_contains_only_safe_evidence() -> None:
    finding = HighToolResultVolume(tool_name="Read", result_bytes=196608)
    assert hasattr(finding, "tool_name")
    assert hasattr(finding, "result_bytes")
    assert not hasattr(finding, "arguments")
    assert not hasattr(finding, "result")
    assert not hasattr(finding, "input")
    assert not hasattr(finding, "output")
    assert not hasattr(finding, "payload")
    assert not hasattr(finding, "path")
    assert not hasattr(finding, "content")
    assert not hasattr(finding, "prompt")


def _failure_rate_finding(name: str, failed_calls: int, total_calls: int) -> HighToolFailureRate:
    divisor = gcd(failed_calls, total_calls)
    return HighToolFailureRate(
        tool_name=name,
        failed_calls=failed_calls,
        total_calls=total_calls,
        failure_rate=FailureRate(numerator=failed_calls // divisor, denominator=total_calls // divisor),
    )


def test_detect_high_tool_failure_rate_no_tools() -> None:
    findings = detect_high_tool_failure_rate(_tools())
    assert findings == ()


def test_detect_high_tool_failure_rate_below_min_calls_even_at_100_percent() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=2, failures=2)))
    assert findings == ()


def test_detect_high_tool_failure_rate_single_failure_below_min_calls() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=1, failures=1)))
    assert findings == ()


def test_detect_high_tool_failure_rate_min_calls_below_rate_threshold() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=3, successes=2, failures=1)))
    assert findings == ()


def test_detect_high_tool_failure_rate_above_min_calls_below_rate_threshold() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=5, successes=3, failures=2)))
    assert findings == ()


def test_detect_high_tool_failure_rate_at_min_calls_and_exact_rate() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=4, successes=2, failures=2)))
    assert findings == (_failure_rate_finding("Bash", failed_calls=2, total_calls=4),)
    assert findings[0].failure_rate == FailureRate(numerator=1, denominator=2)


def test_detect_high_tool_failure_rate_at_min_calls_above_rate() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=3, successes=1, failures=2)))
    assert findings == (_failure_rate_finding("Bash", failed_calls=2, total_calls=3),)
    assert findings[0].failure_rate == FailureRate(numerator=2, denominator=3)


def test_detect_high_tool_failure_rate_above_both_thresholds() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=6, successes=2, failures=4)))
    assert findings == (_failure_rate_finding("Bash", failed_calls=4, total_calls=6),)
    assert findings[0].failure_rate == FailureRate(numerator=2, denominator=3)


def test_detect_high_tool_failure_rate_all_failures() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=3, failures=3)))
    assert findings == (_failure_rate_finding("Bash", failed_calls=3, total_calls=3),)
    assert findings[0].failure_rate == FailureRate(numerator=1, denominator=1)


def test_detect_high_tool_failure_rate_mixed_success_and_failure() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=7, successes=3, failures=4)))
    assert findings == (_failure_rate_finding("Bash", failed_calls=4, total_calls=7),)


def test_detect_high_tool_failure_rate_mixed_below_rate() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=7, successes=4, failures=3)))
    assert findings == ()


def test_detect_high_tool_failure_rate_successful_calls_only() -> None:
    findings = detect_high_tool_failure_rate(_tools(_tool("Bash", calls=8, failures=0)))
    assert findings == ()


def test_detect_high_tool_failure_rate_multiple_tools() -> None:
    findings = detect_high_tool_failure_rate(
        _tools(
            _tool("Read", calls=8, failures=8),
            _tool("Grep", calls=4, successes=2, failures=2),
            _tool("Write", calls=2, failures=2),
            _tool("Edit", calls=5, successes=3, failures=2),
        )
    )
    assert findings == (
        _failure_rate_finding("Grep", failed_calls=2, total_calls=4),
        _failure_rate_finding("Read", failed_calls=8, total_calls=8),
    )


def test_detect_high_tool_failure_rate_deterministic_ordering() -> None:
    findings = detect_high_tool_failure_rate(
        _tools(
            _tool("Zebra", calls=5, failures=5),
            _tool("Apple", calls=4, successes=2, failures=2),
            _tool("Mango", calls=3, failures=3),
        )
    )
    assert findings == (
        _failure_rate_finding("Apple", failed_calls=2, total_calls=4),
        _failure_rate_finding("Mango", failed_calls=3, total_calls=3),
        _failure_rate_finding("Zebra", failed_calls=5, total_calls=5),
    )


def test_compute_insights_keeps_existing_rules_independent_of_failure_rate() -> None:
    insights = compute_insights(
        _tools(
            _tool("Read", calls=8, successes=8, failures=0, result_bytes=196608),
            _tool("Bash", calls=6, successes=2, failures=4, result_bytes=0),
            _tool("Grep", calls=1, result_bytes=147456),
        )
    )
    assert insights.repeated_tool_calls == (
        RepeatedToolCall(tool_name="Bash", call_count=6),
        RepeatedToolCall(tool_name="Read", call_count=8),
    )
    assert insights.repeated_failed_tool_calls == (RepeatedFailedToolCall(tool_name="Bash", failure_count=4),)
    assert insights.high_tool_result_volume == (
        HighToolResultVolume(tool_name="Grep", result_bytes=147456),
        HighToolResultVolume(tool_name="Read", result_bytes=196608),
    )
    assert insights.high_tool_failure_rate == (_failure_rate_finding("Bash", failed_calls=4, total_calls=6),)


def test_high_tool_failure_rate_contains_only_safe_evidence() -> None:
    finding = _failure_rate_finding("Bash", failed_calls=4, total_calls=6)
    assert hasattr(finding, "tool_name")
    assert hasattr(finding, "failed_calls")
    assert hasattr(finding, "total_calls")
    assert hasattr(finding, "failure_rate")
    assert hasattr(finding.failure_rate, "numerator")
    assert hasattr(finding.failure_rate, "denominator")
    assert not hasattr(finding, "arguments")
    assert not hasattr(finding, "result")
    assert not hasattr(finding, "error")
    assert not hasattr(finding, "error_type")
    assert not hasattr(finding, "input")
    assert not hasattr(finding, "output")
    assert not hasattr(finding, "payload")
    assert not hasattr(finding, "path")
    assert not hasattr(finding, "content")
    assert not hasattr(finding, "prompt")
