"""Deterministic insight rules over trace summaries."""

from coding_agent_performance.trace.report import (
    DominantTool,
    HighToolResultVolume,
    Insights,
    RepeatedFailedToolCall,
    RepeatedToolCall,
    ToolStats,
)

REPEATED_TOOL_CALL_THRESHOLD = 3
REPEATED_FAILED_TOOL_CALL_THRESHOLD = 3
HIGH_TOOL_RESULT_VOLUME_THRESHOLD = 128 * 1024
DOMINANT_TOOL_MIN_TOTAL_CALLS = 10
DOMINANT_TOOL_SHARE_THRESHOLD_PERCENT = 60


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
    max_calls = max(breakdown.calls for breakdown in tools.by_name)
    if max_calls * 100 < total_calls * DOMINANT_TOOL_SHARE_THRESHOLD_PERCENT:
        return None
    winner = min(
        (breakdown for breakdown in tools.by_name if breakdown.calls == max_calls),
        key=lambda breakdown: breakdown.name,
    )
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
        dominant_tool=detect_dominant_tool(tools),
    )
