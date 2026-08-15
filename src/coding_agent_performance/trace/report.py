"""Immutable DTOs for a finished trace summary."""

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ToolStats:
    calls: int
    successes: int
    failures: int
    input_bytes: int
    result_bytes: int
    duration_ms: DurationStats
    by_name: tuple[ToolBreakdown, ...]


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
class TraceSummary:
    schema_version: int
    capture: CaptureInfo
    sessions: SessionStats
    model_usage: ModelUsage
    tools: ToolStats
    activity: ActivityStats
    coverage: CoverageStats
