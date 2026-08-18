"""Immutable DTOs for a finished trace summary."""

from dataclasses import dataclass
from math import gcd
from typing import Literal

type UsageSource = Literal["api_request_events", "otel_metrics", "none"]
type CountByName = tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class DurationStats:
    total: int
    average: float | None
    p50: int | None
    p95: int | None


@dataclass(frozen=True, slots=True)
class TokenTotals:
    input: int
    output: int
    cache_read: int
    cache_creation: int


@dataclass(frozen=True, slots=True)
class ModelBreakdown:
    model: str
    requests: int
    estimated_cost_usd_micros: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


@dataclass(frozen=True, slots=True)
class QuerySourceBreakdown:
    query_source: str
    requests: int
    estimated_cost_usd_micros: int


@dataclass(frozen=True, slots=True)
class ToolBreakdown:
    name: str
    calls: int
    successes: int
    failures: int
    success_rate: float | None
    duration_ms_total: int
    duration_ms_average: float | None
    input_bytes: int
    result_bytes: int


@dataclass(frozen=True, slots=True)
class CaptureInfo:
    source: str
    file: str
    envelopes: int
    log_batches: int
    metric_batches: int
    first_received_at: str | None
    last_received_at: str | None


@dataclass(frozen=True, slots=True)
class SessionStats:
    count: int
    prompts: int
    assistant_responses: int
    compactions: int
    subagents_completed: int


@dataclass(frozen=True, slots=True)
class ModelUsage:
    usage_source: UsageSource
    requests: int
    errors: int
    refusals: int
    estimated_cost_usd_micros: int
    tokens: TokenTotals
    duration_ms: DurationStats
    by_model: tuple[ModelBreakdown, ...]
    by_query_source: tuple[QuerySourceBreakdown, ...]


def tool_success_rate_bps(successes: int, calls: int) -> int | None:
    """Return successes per 10,000 calls, or None when there are no calls.

    Uses integer arithmetic so the rate is stable across serialization. This is
    descriptive telemetry, not a quality or performance score.
    """
    if calls == 0:
        return None
    return (successes * 10_000) // calls


@dataclass(frozen=True, slots=True)
class ToolStats:
    calls: int
    successes: int
    failures: int
    input_bytes: int
    result_bytes: int
    duration_ms: DurationStats
    by_name: tuple[ToolBreakdown, ...]

    @property
    def success_rate_bps(self) -> int | None:
        return tool_success_rate_bps(self.successes, self.calls)


@dataclass(frozen=True, slots=True)
class ActiveTimeStats:
    user_seconds: float
    cli_seconds: float


@dataclass(frozen=True, slots=True)
class LinesOfCodeStats:
    added: int
    removed: int


@dataclass(frozen=True, slots=True)
class CodeEditDecisionStats:
    accepted: int
    rejected: int


@dataclass(frozen=True, slots=True)
class ActivityStats:
    active_time: ActiveTimeStats
    lines_of_code: LinesOfCodeStats
    commits: int
    pull_requests: int
    code_edit_decisions: CodeEditDecisionStats


@dataclass(frozen=True, slots=True)
class CoverageStats:
    log_records: int
    metric_points: int
    duplicate_log_records: int
    duplicate_metric_points: int
    unsupported_metric_points: int
    unknown_otlp_values: int
    unknown_events: CountByName
    unknown_metrics: CountByName
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepeatedToolCall:
    tool_name: str
    call_count: int


@dataclass(frozen=True, slots=True)
class RepeatedFailedToolCall:
    tool_name: str
    failure_count: int


@dataclass(frozen=True, slots=True)
class HighToolResultVolume:
    tool_name: str
    result_bytes: int


@dataclass(frozen=True, slots=True)
class FailureRate:
    numerator: int
    denominator: int

    @classmethod
    def reduced(cls, failed_calls: int, total_calls: int) -> FailureRate:
        divisor = gcd(failed_calls, total_calls)
        return cls(numerator=failed_calls // divisor, denominator=total_calls // divisor)


@dataclass(frozen=True, slots=True)
class HighToolFailureRate:
    tool_name: str
    failed_calls: int
    total_calls: int
    failure_rate: FailureRate


@dataclass(frozen=True, slots=True)
class DominantTool:
    tool_name: str
    call_count: int
    total_calls: int
    share_percent: int


@dataclass(frozen=True, slots=True)
class CompactionPressure:
    compaction_count: int


@dataclass(frozen=True, slots=True)
class Insights:
    repeated_tool_calls: tuple[RepeatedToolCall, ...]
    repeated_failed_tool_calls: tuple[RepeatedFailedToolCall, ...]
    high_tool_result_volume: tuple[HighToolResultVolume, ...]
    high_tool_failure_rate: tuple[HighToolFailureRate, ...]
    dominant_tool: DominantTool | None
    compaction_pressure: CompactionPressure | None


@dataclass(frozen=True, slots=True)
class TraceSummary:
    schema_version: int
    capture: CaptureInfo
    sessions: SessionStats
    model_usage: ModelUsage
    tools: ToolStats
    activity: ActivityStats
    coverage: CoverageStats
    insights: Insights
