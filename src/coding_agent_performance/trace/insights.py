"""Deterministic insight rules over trace summaries."""

from collections.abc import Iterable

from coding_agent_performance.trace.report import (
    DominantTool,
    FailureRate,
    HighToolFailureRate,
    HighToolResultVolume,
    Insights,
    RepeatedFailedToolCall,
    RepeatedToolCall,
    ToolBreakdown,
    ToolStats,
)

REPEATED_TOOL_CALL_THRESHOLD = 3
REPEATED_FAILED_TOOL_CALL_THRESHOLD = 3
HIGH_TOOL_RESULT_VOLUME_THRESHOLD = 128 * 1024
HIGH_TOOL_FAILURE_RATE_MIN_CALLS = 3
HIGH_TOOL_FAILURE_RATE_THRESHOLD_NUMERATOR = 1
HIGH_TOOL_FAILURE_RATE_THRESHOLD_DENOMINATOR = 2
DOMINANT_TOOL_MIN_TOTAL_CALLS = 10
DOMINANT_TOOL_SHARE_THRESHOLD_PERCENT = 60


def detect_repeated_tool_calls(tools: ToolStats) -> tuple[RepeatedToolCall, ...]:
    """Identify tools that meet or exceed the repeated-call threshold.

    Returns findings ordered deterministically by tool name.
    """
    return tuple(
        RepeatedToolCall(tool_name=breakdown.name, call_count=breakdown.calls)
        for breakdown in _breakdowns_by_name(tools)
        if breakdown.calls >= REPEATED_TOOL_CALL_THRESHOLD
    )


def detect_repeated_failed_tool_calls(tools: ToolStats) -> tuple[RepeatedFailedToolCall, ...]:
    """Identify tools whose explicit failures meet or exceed the threshold.

    Returns findings ordered deterministically by tool name. Successful calls
    do not increment the failure count.
    """
    return tuple(
        RepeatedFailedToolCall(tool_name=breakdown.name, failure_count=breakdown.failures)
        for breakdown in _breakdowns_by_name(tools)
        if breakdown.failures >= REPEATED_FAILED_TOOL_CALL_THRESHOLD
    )


def detect_high_tool_result_volume(tools: ToolStats) -> tuple[HighToolResultVolume, ...]:
    """Identify tools whose cumulative result bytes meet or exceed the threshold.

    Returns findings ordered deterministically by tool name. The threshold
    applies to per-tool cumulative `result_bytes` within one capture, not to
    any individual tool call.
    """
    return tuple(
        HighToolResultVolume(tool_name=breakdown.name, result_bytes=breakdown.result_bytes)
        for breakdown in _breakdowns_by_name(tools)
        if breakdown.result_bytes >= HIGH_TOOL_RESULT_VOLUME_THRESHOLD
    )


def detect_high_tool_failure_rate(tools: ToolStats) -> tuple[HighToolFailureRate, ...]:
    """Identify tools whose explicit failure rate meets the floor and threshold.

    Returns findings ordered deterministically by tool name. Rate comparison
    uses integer cross-multiplication so threshold checks stay exact.
    """
    return tuple(
        HighToolFailureRate(
            tool_name=breakdown.name,
            failed_calls=breakdown.failures,
            total_calls=breakdown.calls,
            failure_rate=FailureRate.reduced(breakdown.failures, breakdown.calls),
        )
        for breakdown in _breakdowns_by_name(tools)
        if _meets_high_failure_rate(breakdown.calls, breakdown.failures)
    )


def detect_dominant_tool(tools: ToolStats) -> DominantTool | None:
    """Identify a tool that accounts for a large share of capture tool calls.

    Requires at least `DOMINANT_TOOL_MIN_TOTAL_CALLS` total calls and a single
    tool whose share meets `DOMINANT_TOOL_SHARE_THRESHOLD_PERCENT`. Share
    comparisons use integer arithmetic. When multiple tools share the
    qualifying maximum call count, the lexicographically first tool name wins.
    """
    total_calls = tools.calls
    if total_calls < DOMINANT_TOOL_MIN_TOTAL_CALLS or not tools.by_name:
        return None
    winner = min(tools.by_name, key=lambda breakdown: (-breakdown.calls, breakdown.name))
    if not _ratio_at_least(
        winner.calls,
        total_calls,
        DOMINANT_TOOL_SHARE_THRESHOLD_PERCENT,
        100,
    ):
        return None
    return DominantTool(
        tool_name=winner.name,
        call_count=winner.calls,
        total_calls=total_calls,
        share_percent=(winner.calls * 100) // total_calls,
    )


def compute_insights(tools: ToolStats) -> Insights:
    """Compute all deterministic insights for a trace summary."""
    return Insights(
        repeated_tool_calls=detect_repeated_tool_calls(tools),
        repeated_failed_tool_calls=detect_repeated_failed_tool_calls(tools),
        high_tool_result_volume=detect_high_tool_result_volume(tools),
        high_tool_failure_rate=detect_high_tool_failure_rate(tools),
        dominant_tool=detect_dominant_tool(tools),
    )


def _breakdowns_by_name(tools: ToolStats) -> Iterable[ToolBreakdown]:
    return sorted(tools.by_name, key=lambda breakdown: breakdown.name)


def _meets_high_failure_rate(calls: int, failures: int) -> bool:
    return calls >= HIGH_TOOL_FAILURE_RATE_MIN_CALLS and _ratio_at_least(
        failures,
        calls,
        HIGH_TOOL_FAILURE_RATE_THRESHOLD_NUMERATOR,
        HIGH_TOOL_FAILURE_RATE_THRESHOLD_DENOMINATOR,
    )


def _ratio_at_least(
    numerator: int,
    denominator: int,
    threshold_numerator: int,
    threshold_denominator: int,
) -> bool:
    return numerator * threshold_denominator >= denominator * threshold_numerator
