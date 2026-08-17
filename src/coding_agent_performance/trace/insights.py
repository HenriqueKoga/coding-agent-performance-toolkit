"""Deterministic insight rules over trace summaries."""

from coding_agent_performance.trace.report import Insights, RepeatedToolCall, ToolStats

REPEATED_TOOL_CALL_THRESHOLD = 3


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


def compute_insights(tools: ToolStats) -> Insights:
    """Compute all deterministic insights for a trace summary."""
    return Insights(repeated_tool_calls=detect_repeated_tool_calls(tools))
