"""Mutable aggregation state colocated with the behavior that maintains it."""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from coding_agent_performance.trace.capture import CaptureEnvelope
from coding_agent_performance.trace.cost import usd_to_micros
from coding_agent_performance.trace.records import (
    ActivityMeasurement,
    AggregationTemporality,
    MetricKind,
    ModelRequest,
    ToolExecution,
)
from coding_agent_performance.trace.report import (
    ActiveTimeStats,
    ActivityStats,
    CaptureInfo,
    CodeEditDecisionStats,
    CoverageStats,
    DurationStats,
    LinesOfCodeStats,
    ModelBreakdown,
    ModelUsage,
    QuerySourceBreakdown,
    SessionStats,
    TokenTotals,
    ToolBreakdown,
    ToolStats,
    UsageSource,
)

_TOKEN_TYPES: Final = {
    "input": "input",
    "output": "output",
    "cacheRead": "cache_read",
    "cache_read": "cache_read",
    "cacheCreation": "cache_creation",
    "cache_creation": "cache_creation",
}
_USAGE_METRICS: Final = frozenset({"claude_code.token.usage", "claude_code.cost.usage"})

type _SeriesKey = tuple[str, tuple[tuple[str, str], ...], int | None]
type LogIdentity = tuple[str, int, str]


@dataclass(slots=True)
class _ModelBucket:
    requests: int = 0
    estimated_cost_usd_micros: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass(slots=True)
class _QueryBucket:
    requests: int = 0
    estimated_cost_usd_micros: int = 0


@dataclass(slots=True)
class _ToolBucket:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    duration_ms_total: int = 0
    duration_count: int = 0
    input_bytes: int = 0
    result_bytes: int = 0


@dataclass(slots=True)
class _Series:
    kind: MetricKind
    temporality: AggregationTemporality | None
    latest_time: int | None = None
    latest_value: int | float = 0
    delta_total: int | float = 0


@dataclass(frozen=True, slots=True)
class MetricIngestResult:
    duplicate: bool
    unknown_temporality: bool = False


@dataclass(slots=True)
class CaptureAccumulator:
    filename: str
    source: str | None = None
    envelopes: int = 0
    log_batches: int = 0
    metric_batches: int = 0
    first_received_at: datetime | None = None
    last_received_at: datetime | None = None

    def add(self, envelope: CaptureEnvelope) -> None:
        self.envelopes += 1
        self.source = envelope.source
        if envelope.signal == "logs":
            self.log_batches += 1
        else:
            self.metric_batches += 1
        if self.first_received_at is None or envelope.received_at < self.first_received_at:
            self.first_received_at = envelope.received_at
        if self.last_received_at is None or envelope.received_at > self.last_received_at:
            self.last_received_at = envelope.received_at

    def snapshot(self) -> CaptureInfo:
        return CaptureInfo(
            source=self.source or "unknown",
            file=self.filename,
            envelopes=self.envelopes,
            log_batches=self.log_batches,
            metric_batches=self.metric_batches,
            first_received_at=_isoformat(self.first_received_at),
            last_received_at=_isoformat(self.last_received_at),
        )


@dataclass(slots=True)
class SessionAccumulator:
    ids: set[str] = field(default_factory=set)
    prompts: int = 0
    assistant_responses: int = 0
    compactions: int = 0
    subagents_completed: int = 0

    def add_id(self, session_id: str) -> None:
        self.ids.add(session_id)

    def add_prompt(self) -> None:
        self.prompts += 1

    def add_assistant_response(self) -> None:
        self.assistant_responses += 1

    def add_compaction(self) -> None:
        self.compactions += 1

    def add_subagent_completed(self) -> None:
        self.subagents_completed += 1

    def snapshot(self, *, metric_session_count: int) -> SessionStats:
        return SessionStats(
            count=len(self.ids) if self.ids else metric_session_count,
            prompts=self.prompts,
            assistant_responses=self.assistant_responses,
            compactions=self.compactions,
            subagents_completed=self.subagents_completed,
        )


@dataclass(slots=True)
class UsageAccumulator:
    requests: int = 0
    errors: int = 0
    refusals: int = 0
    event_cost: int = 0
    event_tokens: TokenTotals = field(default_factory=lambda: TokenTotals(0, 0, 0, 0))
    request_durations: list[int] = field(default_factory=list)
    by_model: dict[str, _ModelBucket] = field(default_factory=dict)
    by_query: dict[str, _QueryBucket] = field(default_factory=dict)
    cost_complete: bool = True
    input_complete: bool = True
    output_complete: bool = True

    def add_request(self, record: ModelRequest) -> None:
        self.requests += 1
        if not record.has_estimated_cost_usd_micros:
            self.cost_complete = False
        if not record.has_input_tokens:
            self.input_complete = False
        if not record.has_output_tokens:
            self.output_complete = False
        self.event_cost += record.estimated_cost_usd_micros
        self.event_tokens = TokenTotals(
            input=self.event_tokens.input + record.input_tokens,
            output=self.event_tokens.output + record.output_tokens,
            cache_read=self.event_tokens.cache_read + record.cache_read_tokens,
            cache_creation=self.event_tokens.cache_creation + record.cache_creation_tokens,
        )
        if record.duration_ms is not None:
            self.request_durations.append(record.duration_ms)
        bucket = self.by_model.setdefault(record.model, _ModelBucket())
        bucket.requests += 1
        bucket.estimated_cost_usd_micros += record.estimated_cost_usd_micros
        bucket.input_tokens += record.input_tokens
        bucket.output_tokens += record.output_tokens
        bucket.cache_read_tokens += record.cache_read_tokens
        bucket.cache_creation_tokens += record.cache_creation_tokens
        if record.query_source:
            query = self.by_query.setdefault(record.query_source, _QueryBucket())
            query.requests += 1
            query.estimated_cost_usd_micros += record.estimated_cost_usd_micros

    def add_error(self) -> None:
        self.errors += 1

    def add_refusal(self) -> None:
        self.refusals += 1

    def snapshot(self, metrics: MetricAccumulator) -> ModelUsage:
        if self.requests > 0:
            return ModelUsage(
                usage_source="api_request_events",
                requests=self.requests,
                errors=self.errors,
                refusals=self.refusals,
                estimated_cost_usd_micros=self.event_cost,
                tokens=self.event_tokens,
                duration_ms=duration_stats(self.request_durations),
                by_model=self._event_model_rows(),
                by_query_source=self._event_query_rows(),
            )
        tokens, cost, by_model, by_query = metrics.usage_totals()
        usage_source: UsageSource = "otel_metrics" if metrics.has_usage_metrics() else "none"
        return ModelUsage(
            usage_source=usage_source,
            requests=0,
            errors=self.errors,
            refusals=self.refusals,
            estimated_cost_usd_micros=cost,
            tokens=tokens,
            duration_ms=duration_stats([]),
            by_model=by_model,
            by_query_source=by_query,
        )

    def _event_model_rows(self) -> tuple[ModelBreakdown, ...]:
        rows = [
            ModelBreakdown(
                model=name,
                requests=bucket.requests,
                estimated_cost_usd_micros=bucket.estimated_cost_usd_micros,
                input_tokens=bucket.input_tokens,
                output_tokens=bucket.output_tokens,
                cache_read_tokens=bucket.cache_read_tokens,
                cache_creation_tokens=bucket.cache_creation_tokens,
            )
            for name, bucket in self.by_model.items()
        ]
        rows.sort(key=lambda row: row.model)
        return tuple(rows)

    def _event_query_rows(self) -> tuple[QuerySourceBreakdown, ...]:
        rows = [
            QuerySourceBreakdown(
                query_source=name,
                requests=bucket.requests,
                estimated_cost_usd_micros=bucket.estimated_cost_usd_micros,
            )
            for name, bucket in self.by_query.items()
        ]
        rows.sort(key=lambda row: row.query_source)
        return tuple(rows)


@dataclass(slots=True)
class ToolAccumulator:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    input_bytes: int = 0
    result_bytes: int = 0
    durations: list[int] = field(default_factory=list)
    by_name: dict[str, _ToolBucket] = field(default_factory=dict)
    success_complete: bool = True
    result_bytes_complete: bool = True

    def add(self, record: ToolExecution) -> None:
        self.calls += 1
        if not record.success_valid:
            self.success_complete = False
        if record.result_size_bytes is None:
            self.result_bytes_complete = False
        if record.success:
            self.successes += 1
        else:
            self.failures += 1
        input_bytes = record.input_size_bytes or 0
        result_bytes = record.result_size_bytes or 0
        self.input_bytes += input_bytes
        self.result_bytes += result_bytes
        bucket = self.by_name.setdefault(record.tool_name, _ToolBucket())
        bucket.calls += 1
        if record.success:
            bucket.successes += 1
        else:
            bucket.failures += 1
        if record.duration_ms is not None:
            self.durations.append(record.duration_ms)
            bucket.duration_ms_total += record.duration_ms
            bucket.duration_count += 1
        bucket.input_bytes += input_bytes
        bucket.result_bytes += result_bytes

    def snapshot(self) -> ToolStats:
        rows = [
            ToolBreakdown(
                name=name,
                calls=bucket.calls,
                successes=bucket.successes,
                failures=bucket.failures,
                success_rate=(bucket.successes / bucket.calls) if bucket.calls else None,
                duration_ms_total=bucket.duration_ms_total,
                duration_ms_average=(
                    round(bucket.duration_ms_total / bucket.duration_count, 2) if bucket.duration_count else None
                ),
                input_bytes=bucket.input_bytes,
                result_bytes=bucket.result_bytes,
            )
            for name, bucket in self.by_name.items()
        ]
        rows.sort(key=lambda row: row.name)
        return ToolStats(
            calls=self.calls,
            successes=self.successes,
            failures=self.failures,
            input_bytes=self.input_bytes,
            result_bytes=self.result_bytes,
            duration_ms=duration_stats(self.durations),
            by_name=tuple(rows),
        )


@dataclass(slots=True)
class MetricAccumulator:
    seen_points: set[tuple[_SeriesKey, int]] = field(default_factory=set)
    series: dict[_SeriesKey, _Series] = field(default_factory=dict)

    def add(self, record: ActivityMeasurement) -> MetricIngestResult:
        key = (record.name, record.attributes, record.start_time_unix_nano)
        if record.time_unix_nano is not None:
            point_id = (key, record.time_unix_nano)
            if point_id in self.seen_points:
                return MetricIngestResult(duplicate=True)
            self.seen_points.add(point_id)
        unknown_temporality = record.kind == "sum" and record.aggregation_temporality is None
        series = self.series.get(key)
        if series is None:
            series = _Series(kind=record.kind, temporality=record.aggregation_temporality)
            self.series[key] = series
        if record.kind == "sum" and record.aggregation_temporality == "delta":
            series.delta_total = _add_number(series.delta_total, record.value)
        if _is_newer(record.time_unix_nano, series.latest_time):
            series.latest_time = record.time_unix_nano
            series.latest_value = record.value
        return MetricIngestResult(duplicate=False, unknown_temporality=unknown_temporality)

    def has_usage_metrics(self) -> bool:
        return any(key[0] in _USAGE_METRICS for key in self.series)

    def has_cost_usage(self) -> bool:
        return any(key[0] == "claude_code.cost.usage" for key in self.series)

    def has_token_usage(self, token_type: str) -> bool:
        for name, attrs, _start in self.series:
            if name != "claude_code.token.usage":
                continue
            if _TOKEN_TYPES.get(dict(attrs).get("type", "")) == token_type:
                return True
        return False

    def total(self, name: str) -> int | float:
        value: int | float = 0
        for key, series in self.series.items():
            if key[0] == name:
                value = _add_number(value, _resolved_value(series))
        return value

    def usage_totals(self) -> tuple[TokenTotals, int, tuple[ModelBreakdown, ...], tuple[QuerySourceBreakdown, ...]]:
        tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        models: dict[str, _ModelBucket] = {}
        queries: dict[str, _QueryBucket] = {}
        cost = 0
        for key, series in self.series.items():
            name, attrs, _start = key
            attr_map = dict(attrs)
            value = _resolved_value(series)
            if name == "claude_code.token.usage":
                token_type = _TOKEN_TYPES.get(attr_map.get("type", ""))
                if token_type is None:
                    continue
                amount = int(value)
                tokens[token_type] += amount
                model = attr_map.get("model")
                if model:
                    bucket = models.setdefault(model, _ModelBucket())
                    match token_type:
                        case "input":
                            bucket.input_tokens += amount
                        case "output":
                            bucket.output_tokens += amount
                        case "cache_read":
                            bucket.cache_read_tokens += amount
                        case "cache_creation":
                            bucket.cache_creation_tokens += amount
                query = attr_map.get("query_source")
                if query:
                    queries.setdefault(query, _QueryBucket())
            elif name == "claude_code.cost.usage":
                micros = usd_to_micros(value)
                cost += micros
                model = attr_map.get("model")
                if model:
                    models.setdefault(model, _ModelBucket()).estimated_cost_usd_micros += micros
                query = attr_map.get("query_source")
                if query:
                    queries.setdefault(query, _QueryBucket()).estimated_cost_usd_micros += micros
        by_model = tuple(
            ModelBreakdown(
                model=name,
                requests=bucket.requests,
                estimated_cost_usd_micros=bucket.estimated_cost_usd_micros,
                input_tokens=bucket.input_tokens,
                output_tokens=bucket.output_tokens,
                cache_read_tokens=bucket.cache_read_tokens,
                cache_creation_tokens=bucket.cache_creation_tokens,
            )
            for name, bucket in sorted(models.items())
        )
        by_query = tuple(
            QuerySourceBreakdown(
                query_source=name,
                requests=bucket.requests,
                estimated_cost_usd_micros=bucket.estimated_cost_usd_micros,
            )
            for name, bucket in sorted(queries.items())
        )
        return (
            TokenTotals(
                input=tokens["input"],
                output=tokens["output"],
                cache_read=tokens["cache_read"],
                cache_creation=tokens["cache_creation"],
            ),
            cost,
            by_model,
            by_query,
        )

    def activity_stats(self) -> ActivityStats:
        user_seconds = 0.0
        cli_seconds = 0.0
        added = 0
        removed = 0
        accepted = 0
        rejected = 0
        commits = 0
        pull_requests = 0
        for key, series in self.series.items():
            name, attrs, _start = key
            if name in _USAGE_METRICS:
                continue
            attr_map = dict(attrs)
            value = _resolved_value(series)
            if name == "claude_code.active_time.total":
                kind = attr_map.get("type")
                if kind == "user":
                    user_seconds += float(value)
                elif kind == "cli":
                    cli_seconds += float(value)
            elif name == "claude_code.lines_of_code.count":
                kind = attr_map.get("type")
                if kind == "added":
                    added += int(value)
                elif kind == "removed":
                    removed += int(value)
            elif name == "claude_code.commit.count":
                commits += int(value)
            elif name == "claude_code.pull_request.count":
                pull_requests += int(value)
            elif name == "claude_code.code_edit_tool.decision":
                decision = attr_map.get("decision")
                if decision == "accept":
                    accepted += int(value)
                elif decision == "reject":
                    rejected += int(value)
        return ActivityStats(
            active_time=ActiveTimeStats(user_seconds=user_seconds, cli_seconds=cli_seconds),
            lines_of_code=LinesOfCodeStats(added=added, removed=removed),
            commits=commits,
            pull_requests=pull_requests,
            code_edit_decisions=CodeEditDecisionStats(accepted=accepted, rejected=rejected),
        )


@dataclass(slots=True)
class CoverageAccumulator:
    log_records: int = 0
    metric_points: int = 0
    duplicate_logs: int = 0
    duplicate_points: int = 0
    unsupported: int = 0
    unknown_otlp_values: int = 0
    unknown_events: dict[str, int] = field(default_factory=dict)
    unknown_metrics: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    seen_logs: set[LogIdentity] = field(default_factory=set)
    temporality_warned: bool = False

    def add_counts(
        self,
        *,
        log_count: int,
        metric_count: int,
        unsupported: int,
        unknown_otlp_values: int,
    ) -> None:
        self.log_records += log_count
        self.metric_points += metric_count
        self.unsupported += unsupported
        self.unknown_otlp_values += unknown_otlp_values

    def observe_log(self, identity: LogIdentity) -> bool:
        if identity in self.seen_logs:
            self.duplicate_logs += 1
            return False
        self.seen_logs.add(identity)
        return True

    def record_duplicate_point(self) -> None:
        self.duplicate_points += 1

    def record_unknown_event(self, name: str) -> None:
        self.unknown_events[name] = self.unknown_events.get(name, 0) + 1

    def record_unknown_metric(self, name: str) -> None:
        self.unknown_metrics[name] = self.unknown_metrics.get(name, 0) + 1

    def warn_temporality(self) -> None:
        if self.temporality_warned:
            return
        self.warnings.append("missing or unknown aggregation temporality; using latest datapoint per series")
        self.temporality_warned = True

    def has_recognized_telemetry(self) -> bool:
        return self.log_records > 0 or self.metric_points > 0 or self.unsupported > 0

    def snapshot(self) -> CoverageStats:
        return CoverageStats(
            log_records=self.log_records,
            metric_points=self.metric_points,
            duplicate_log_records=self.duplicate_logs,
            duplicate_metric_points=self.duplicate_points,
            unsupported_metric_points=self.unsupported,
            unknown_otlp_values=self.unknown_otlp_values,
            unknown_events=tuple(sorted(self.unknown_events.items())),
            unknown_metrics=tuple(sorted(self.unknown_metrics.items())),
            warnings=tuple(self.warnings),
        )


def duration_stats(values: list[int]) -> DurationStats:
    if not values:
        return DurationStats(total=0, average=None, p50=None, p95=None)
    total = sum(values)
    return DurationStats(
        total=total,
        average=round(total / len(values), 2),
        p50=nearest_rank(values, 0.50),
        p95=nearest_rank(values, 0.95),
    )


def nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[index]


def _resolved_value(series: _Series) -> int | float:
    if series.kind == "sum" and series.temporality == "delta":
        return series.delta_total
    return series.latest_value


def _is_newer(candidate: int | None, current: int | None) -> bool:
    if candidate is None:
        return current is None
    if current is None:
        return True
    return candidate >= current


def _add_number(left: int | float, right: int | float) -> int | float:
    total = left + right
    if isinstance(total, float) and not math.isfinite(total):
        return 0
    return total


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
