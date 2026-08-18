"""Pure compact extract from an immutable trace summary."""

from dataclasses import dataclass
from typing import Final

from coding_agent_performance.trace.report import Insights, SessionStats, TraceSummary, UsageSource

HANDOFF_SCHEMA_VERSION: Final = 1
HANDOFF_CAPTURE_SOURCES: Final = frozenset({"claude-code"})
HANDOFF_UNKNOWN_SOURCE: Final = "unknown"


@dataclass(frozen=True, slots=True)
class HandoffCapture:
    source: str
    file: str


@dataclass(frozen=True, slots=True)
class HandoffTokens:
    input: int
    output: int


@dataclass(frozen=True, slots=True)
class HandoffModelUsage:
    usage_source: UsageSource
    requests: int
    errors: int
    refusals: int
    estimated_cost_usd_micros: int
    tokens: HandoffTokens


@dataclass(frozen=True, slots=True)
class HandoffTools:
    calls: int
    successes: int
    failures: int
    result_bytes: int
    success_rate_bps: int | None


@dataclass(frozen=True, slots=True)
class TraceHandoff:
    schema_version: int
    capture: HandoffCapture
    sessions: SessionStats
    model_usage: HandoffModelUsage
    tools: HandoffTools
    insights: Insights


def handoff_from_summary(summary: TraceSummary) -> TraceHandoff:
    usage = summary.model_usage
    tools = summary.tools
    return TraceHandoff(
        schema_version=HANDOFF_SCHEMA_VERSION,
        capture=HandoffCapture(
            source=_allowlisted_source(summary.capture.source),
            file=summary.capture.file,
        ),
        sessions=summary.sessions,
        model_usage=HandoffModelUsage(
            usage_source=usage.usage_source,
            requests=usage.requests,
            errors=usage.errors,
            refusals=usage.refusals,
            estimated_cost_usd_micros=usage.estimated_cost_usd_micros,
            tokens=HandoffTokens(input=usage.tokens.input, output=usage.tokens.output),
        ),
        tools=HandoffTools(
            calls=tools.calls,
            successes=tools.successes,
            failures=tools.failures,
            result_bytes=tools.result_bytes,
            success_rate_bps=tools.success_rate_bps,
        ),
        insights=summary.insights,
    )


def _allowlisted_source(source: str) -> str:
    if source in HANDOFF_CAPTURE_SOURCES:
        return source
    return HANDOFF_UNKNOWN_SOURCE
