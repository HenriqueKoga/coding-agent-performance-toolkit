"""Deterministic insight rules over trace summaries."""

from math import gcd

from coding_agent_performance.trace.report import (
    FailureRate,
    HighToolFailureRate,
    HighToolResultVolume,
    Insights,
    RepeatedFailedToolCall,
    RepeatedToolCall,
    ToolStats,
)

REPEATED_TOOL_CALL_THRESHOLD = 3
REPEATED_FAILED_TOOL_CALL_THRESHOLD = 3
HIGH_TOOL_RESULT_VOLUME_THRESHOLD = 128 * 1024
HIGH_TOOL_FAILURE_RATE_MIN_CALLS = 3
HIGH_TOOL_FAILURE_RATE_THRESHOLD_NUMERATOR = 1
HIGH_TOOL_FAILURE_RATE_THRESHOLD_DENOMINATOR = 2


def detect_repeated_tool_calls(tools: ToolStats) -> tuple[RepeatedToolCall, ...]:
    """Identify tools that meet or exceed the repeated-call threshold.

    Returns findings ordered deterministically by tool name.
    """
    findings = [
        RepeatedToolCall(tool_name=breakdown.name, call_count=breakdown.calls)
        for breakdown in tools.by_name
        if breakdown.calls >= REPEATED_TOOL_CALL_THRESHOLD
    ]
    findings.sort(key=lambda f: f.tool_name)
    return tuple(findings)


def detect_repeated_failed_tool_calls(tools: ToolStats) -> tuple[RepeatedFailedToolCall, ...]:
    """Identify tools whose explicit failures meet or exceed the threshold.

    Returns findings ordered deterministically by tool name. Successful calls
    do not increment the failure count.
    """
    findings = [
        RepeatedFailedToolCall(tool_name=breakdown.name, failure_count=breakdown.failures)
        for breakdown in tools.by_name
        if breakdown.failures >= REPEATED_FAILED_TOOL_CALL_THRESHOLD
    ]
    findings.sort(key=lambda f: f.tool_name)
    return tuple(findings)


def detect_high_tool_result_volume(tools: ToolStats) -> tuple[HighToolResultVolume, ...]:
    """Identify tools whose cumulative result bytes meet or exceed the threshold.

    Returns findings ordered deterministically by tool name. The threshold
    applies to per-tool cumulative `result_bytes` within one capture, not to
    any individual tool call.
    """
    findings = [
        HighToolResultVolume(tool_name=breakdown.name, result_bytes=breakdown.result_bytes)
        for breakdown in tools.by_name
        if breakdown.result_bytes >= HIGH_TOOL_RESULT_VOLUME_THRESHOLD
    ]
    findings.sort(key=lambda f: f.tool_name)
    return tuple(findings)


def detect_high_tool_failure_rate(tools: ToolStats) -> tuple[HighToolFailureRate, ...]:
    """Identify tools whose explicit failure rate meets the floor and threshold.

    Returns findings ordered deterministically by tool name. Rate comparison
    uses integer cross-multiplication so threshold checks stay exact.
    """
    findings = [
        HighToolFailureRate(
            tool_name=breakdown.name,
            failed_calls=breakdown.failures,
            total_calls=breakdown.calls,
            failure_rate=_exact_failure_rate(breakdown.failures, breakdown.calls),
        )
        for breakdown in tools.by_name
        if _meets_high_failure_rate(breakdown.calls, breakdown.failures)
    ]
    findings.sort(key=lambda f: f.tool_name)
    return tuple(findings)


def compute_insights(tools: ToolStats) -> Insights:
    """Compute all deterministic insights for a trace summary."""
    return Insights(
        repeated_tool_calls=detect_repeated_tool_calls(tools),
        repeated_failed_tool_calls=detect_repeated_failed_tool_calls(tools),
        high_tool_result_volume=detect_high_tool_result_volume(tools),
        high_tool_failure_rate=detect_high_tool_failure_rate(tools),
    )


def _meets_high_failure_rate(calls: int, failures: int) -> bool:
    if calls < HIGH_TOOL_FAILURE_RATE_MIN_CALLS:
        return False
    return failures * HIGH_TOOL_FAILURE_RATE_THRESHOLD_DENOMINATOR >= calls * HIGH_TOOL_FAILURE_RATE_THRESHOLD_NUMERATOR


def _exact_failure_rate(failed_calls: int, total_calls: int) -> FailureRate:
    divisor = gcd(failed_calls, total_calls)
    return FailureRate(numerator=failed_calls // divisor, denominator=total_calls // divisor)
