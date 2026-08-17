"""Deterministic insight rules over immutable summary evidence."""

from dataclasses import dataclass

from coding_agent_performance.trace.report import (
    HighToolResultVolume,
    Insights,
    RepeatedFailedToolCall,
    RepeatedToolCall,
    ToolStats,
)

REPEATED_TOOL_CALL_THRESHOLD = 3
REPEATED_FAILED_TOOL_CALL_THRESHOLD = 3
HIGH_TOOL_RESULT_VOLUME_THRESHOLD = 128 * 1024


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


@dataclass(frozen=True, slots=True)
class InsightAnalyzer:
    """Produce deterministic insights from provider-neutral summary evidence."""

    tools: ToolStats

    def analyze(self) -> Insights:
        return Insights(
            repeated_tool_calls=detect_repeated_tool_calls(self.tools),
            repeated_failed_tool_calls=detect_repeated_failed_tool_calls(self.tools),
            high_tool_result_volume=detect_high_tool_result_volume(self.tools),
        )


def compute_insights(tools: ToolStats) -> Insights:
    """Compute all deterministic insights for a trace summary."""
    return InsightAnalyzer(tools=tools).analyze()
