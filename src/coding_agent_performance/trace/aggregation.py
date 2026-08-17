"""Incremental aggregation of domain records into a trace summary."""

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

from coding_agent_performance.trace.capture import CaptureEnvelope, CaptureError
from coding_agent_performance.trace.cost import usd_to_micros
from coding_agent_performance.trace.insights import compute_insights
from coding_agent_performance.trace.records import (
    ActivityMeasurement,
    AggregationTemporality,
    AssistantResponse,
    DomainRecord,
    MetricKind,
    ModelRequest,
    ModelRequestError,
    NamedLifecycleEvent,
    ToolExecution,
    UnknownEvent,
    UnknownMetric,
    UserPrompt,
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
    TraceSummary,
)

SUMMARY_SCHEMA_VERSION: Final = 1
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


@dataclass(slots=True)
class _CaptureState:
    filename: str
    source: str | None = None
    envelopes: int = 0
    log_batches: int = 0
    metric_batches: int = 0
    first_received_at: datetime | None = None
    last_received_at: datetime | None = None


@dataclass(slots=True)
class _SessionState:
    ids: set[str] = field(default_factory=set)
    prompts: int = 0
    assistant_responses: int = 0
    compactions: int = 0
    subagents_completed: int = 0


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
class _UsageState:
    requests: int = 0
    errors: int = 0
    refusals: int = 0
    event_cost: int = 0
    event_tokens: TokenTotals = field(default_factory=lambda: TokenTotals(0, 0, 0, 0))
    request_durations: list[int] = field(default_factory=list)
    by_model: dict[str, _ModelBucket] = field(default_factory=dict)
    by_query: dict[str, _QueryBucket] = field(default_factory=dict)


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
class _ToolState:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    input_bytes: int = 0
    result_bytes: int = 0
    durations: list[int] = field(default_factory=list)
    by_name: dict[str, _ToolBucket] = field(default_factory=dict)


@dataclass(slots=True)
class _Series:
    kind: MetricKind
    temporality: AggregationTemporality | None
    latest_time: int | None = None
    latest_value: int | float = 0
    delta_total: int | float = 0


@dataclass(slots=True)
class _MetricState:
    seen_points: set[tuple[_SeriesKey, int]] = field(default_factory=set)
    series: dict[_SeriesKey, _Series] = field(default_factory=dict)


@dataclass(slots=True)
class _CoverageState:
    log_records: int = 0
    metric_points: int = 0
    duplicate_logs: int = 0
    duplicate_points: int = 0
    unsupported: int = 0
    unknown_otlp_values: int = 0
    unknown_events: dict[str, int] = field(default_factory=dict)
    unknown_metrics: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    seen_logs: set[tuple[str, int, str]] = field(default_factory=set)
    temporality_warned: bool = False


class IncrementalSummarizer:
    """Accumulate normalized records without retaining raw payloads."""

    def __init__(self, filename: str) -> None:
        self._capture = _CaptureState(filename=filename)
        self._sessions = _SessionState()
        self._usage = _UsageState()
        self._tools = _ToolState()
        self._metrics = _MetricState()
        self._coverage = _CoverageState()

    def add(
        self,
        envelope: CaptureEnvelope,
        records: tuple[DomainRecord, ...],
        *,
        log_count: int,
        metric_count: int,
        unsupported: int,
        unknown_otlp_values: int = 0,
    ) -> None:
        capture = self._capture
        capture.envelopes += 1
        capture.source = envelope.source
        if envelope.signal == "logs":
            capture.log_batches += 1
        else:
            capture.metric_batches += 1
        if capture.first_received_at is None or envelope.received_at < capture.first_received_at:
            capture.first_received_at = envelope.received_at
        if capture.last_received_at is None or envelope.received_at > capture.last_received_at:
            capture.last_received_at = envelope.received_at
        self._coverage.log_records += log_count
        self._coverage.metric_points += metric_count
        self._coverage.unsupported += unsupported
        self._coverage.unknown_otlp_values += unknown_otlp_values
        for record in records:
            self._ingest(record)

    def finish(self, path: Path) -> TraceSummary:
        coverage = self._coverage
        if coverage.log_records == 0 and coverage.metric_points == 0 and coverage.unsupported == 0:
            raise CaptureError(path, "no recognized telemetry")
        capture = self._capture
        sessions = self._sessions
        tools = self._tool_stats()
        return TraceSummary(
            schema_version=SUMMARY_SCHEMA_VERSION,
            capture=CaptureInfo(
                source=capture.source or "unknown",
                file=capture.filename,
                envelopes=capture.envelopes,
                log_batches=capture.log_batches,
                metric_batches=capture.metric_batches,
                first_received_at=_isoformat(capture.first_received_at),
                last_received_at=_isoformat(capture.last_received_at),
            ),
            sessions=SessionStats(
                count=self._session_count(),
                prompts=sessions.prompts,
                assistant_responses=sessions.assistant_responses,
                compactions=sessions.compactions,
                subagents_completed=sessions.subagents_completed,
            ),
            model_usage=self._model_usage(),
            tools=tools,
            activity=self._activity_stats(),
            coverage=CoverageStats(
                log_records=coverage.log_records,
                metric_points=coverage.metric_points,
                duplicate_log_records=coverage.duplicate_logs,
                duplicate_metric_points=coverage.duplicate_points,
                unsupported_metric_points=coverage.unsupported,
                unknown_otlp_values=coverage.unknown_otlp_values,
                unknown_events=tuple(sorted(coverage.unknown_events.items())),
                unknown_metrics=tuple(sorted(coverage.unknown_metrics.items())),
                warnings=tuple(coverage.warnings),
            ),
            insights=compute_insights(tools),
        )

    def _ingest(self, record: DomainRecord) -> None:
        if isinstance(record, ActivityMeasurement):
            self._ingest_measurement(record)
            return
        if isinstance(record, UnknownMetric):
            counts = self._coverage.unknown_metrics
            counts[record.name] = counts.get(record.name, 0) + 1
            return
        identity = _log_identity(record)
        if identity is not None:
            if identity in self._coverage.seen_logs:
                self._coverage.duplicate_logs += 1
                return
            self._coverage.seen_logs.add(identity)
        session_id = getattr(record, "session_id", None)
        if isinstance(session_id, str) and session_id:
            self._sessions.ids.add(session_id)
        if isinstance(record, ModelRequest):
            self._ingest_request(record)
        elif isinstance(record, ModelRequestError):
            self._usage.errors += 1
        elif isinstance(record, ToolExecution):
            self._ingest_tool(record)
        elif isinstance(record, UserPrompt):
            self._sessions.prompts += 1
        elif isinstance(record, AssistantResponse):
            self._sessions.assistant_responses += 1
        elif isinstance(record, NamedLifecycleEvent):
            if record.name == "api_refusal":
                self._usage.refusals += 1
            elif record.name == "compaction":
                self._sessions.compactions += 1
            elif record.name == "subagent_completed":
                self._sessions.subagents_completed += 1
        elif isinstance(record, UnknownEvent):
            counts = self._coverage.unknown_events
            counts[record.name] = counts.get(record.name, 0) + 1

    def _ingest_request(self, record: ModelRequest) -> None:
        usage = self._usage
        usage.requests += 1
        usage.event_cost += record.estimated_cost_usd_micros
        usage.event_tokens = TokenTotals(
            input=usage.event_tokens.input + record.input_tokens,
            output=usage.event_tokens.output + record.output_tokens,
            cache_read=usage.event_tokens.cache_read + record.cache_read_tokens,
            cache_creation=usage.event_tokens.cache_creation + record.cache_creation_tokens,
        )
        if record.duration_ms is not None:
            usage.request_durations.append(record.duration_ms)
        bucket = usage.by_model.setdefault(record.model, _ModelBucket())
        bucket.requests += 1
        bucket.estimated_cost_usd_micros += record.estimated_cost_usd_micros
        bucket.input_tokens += record.input_tokens
        bucket.output_tokens += record.output_tokens
        bucket.cache_read_tokens += record.cache_read_tokens
        bucket.cache_creation_tokens += record.cache_creation_tokens
        if record.query_source:
            query = usage.by_query.setdefault(record.query_source, _QueryBucket())
            query.requests += 1
            query.estimated_cost_usd_micros += record.estimated_cost_usd_micros

    def _ingest_tool(self, record: ToolExecution) -> None:
        tools = self._tools
        tools.calls += 1
        if record.success:
            tools.successes += 1
        else:
            tools.failures += 1
        input_bytes = record.input_size_bytes or 0
        result_bytes = record.result_size_bytes or 0
        tools.input_bytes += input_bytes
        tools.result_bytes += result_bytes
        bucket = tools.by_name.setdefault(record.tool_name, _ToolBucket())
        bucket.calls += 1
        if record.success:
            bucket.successes += 1
        else:
            bucket.failures += 1
        if record.duration_ms is not None:
            tools.durations.append(record.duration_ms)
            bucket.duration_ms_total += record.duration_ms
            bucket.duration_count += 1
        bucket.input_bytes += input_bytes
        bucket.result_bytes += result_bytes

    def _ingest_measurement(self, record: ActivityMeasurement) -> None:
        key = (record.name, record.attributes, record.start_time_unix_nano)
        if record.time_unix_nano is not None:
            point_id = (key, record.time_unix_nano)
            if point_id in self._metrics.seen_points:
                self._coverage.duplicate_points += 1
                return
            self._metrics.seen_points.add(point_id)
        if record.kind == "sum" and record.aggregation_temporality is None:
            self._warn_temporality()
        series = self._metrics.series.get(key)
        if series is None:
            series = _Series(kind=record.kind, temporality=record.aggregation_temporality)
            self._metrics.series[key] = series
        if record.kind == "sum" and record.aggregation_temporality == "delta":
            series.delta_total = _add_number(series.delta_total, record.value)
        if _is_newer(record.time_unix_nano, series.latest_time):
            series.latest_time = record.time_unix_nano
            series.latest_value = record.value

    def _warn_temporality(self) -> None:
        if self._coverage.temporality_warned:
            return
        self._coverage.warnings.append("missing or unknown aggregation temporality; using latest datapoint per series")
        self._coverage.temporality_warned = True

    def _session_count(self) -> int:
        if self._sessions.ids:
            return len(self._sessions.ids)
        return int(self._metric_total("claude_code.session.count"))

    def _model_usage(self) -> ModelUsage:
        usage = self._usage
        if usage.requests > 0:
            return ModelUsage(
                usage_source="api_request_events",
                requests=usage.requests,
                errors=usage.errors,
                refusals=usage.refusals,
                estimated_cost_usd_micros=usage.event_cost,
                tokens=usage.event_tokens,
                duration_ms=duration_stats(usage.request_durations),
                by_model=self._event_model_rows(),
                by_query_source=self._event_query_rows(),
            )
        tokens, cost, by_model, by_query = self._metric_usage()
        has_usage_metrics = any(key[0] in _USAGE_METRICS for key in self._metrics.series)
        return ModelUsage(
            usage_source="otel_metrics" if has_usage_metrics else "none",
            requests=0,
            errors=usage.errors,
            refusals=usage.refusals,
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
            for name, bucket in self._usage.by_model.items()
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
            for name, bucket in self._usage.by_query.items()
        ]
        rows.sort(key=lambda row: row.query_source)
        return tuple(rows)

    def _metric_usage(self) -> tuple[TokenTotals, int, tuple[ModelBreakdown, ...], tuple[QuerySourceBreakdown, ...]]:
        tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        models: dict[str, _ModelBucket] = {}
        queries: dict[str, _QueryBucket] = {}
        cost = 0
        for key, series in self._metrics.series.items():
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

    def _tool_stats(self) -> ToolStats:
        tools = self._tools
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
            for name, bucket in tools.by_name.items()
        ]
        rows.sort(key=lambda row: row.name)
        return ToolStats(
            calls=tools.calls,
            successes=tools.successes,
            failures=tools.failures,
            input_bytes=tools.input_bytes,
            result_bytes=tools.result_bytes,
            duration_ms=duration_stats(tools.durations),
            by_name=tuple(rows),
        )

    def _activity_stats(self) -> ActivityStats:
        user_seconds = 0.0
        cli_seconds = 0.0
        added = 0
        removed = 0
        accepted = 0
        rejected = 0
        commits = 0
        pull_requests = 0
        for key, series in self._metrics.series.items():
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

    def _metric_total(self, name: str) -> int | float:
        total: int | float = 0
        for key, series in self._metrics.series.items():
            if key[0] == name:
                total = _add_number(total, _resolved_value(series))
        return total


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


def _log_identity(record: DomainRecord) -> tuple[str, int, str] | None:
    name = _record_name(record)
    session_id = getattr(record, "session_id", None)
    sequence = getattr(record, "event_sequence", None)
    if isinstance(session_id, str) and session_id and isinstance(sequence, int) and name:
        return session_id, sequence, name
    return None


def _record_name(record: DomainRecord) -> str | None:
    if isinstance(record, ModelRequest):
        return "api_request"
    if isinstance(record, ModelRequestError):
        return "api_error"
    if isinstance(record, ToolExecution):
        return "tool_result"
    if isinstance(record, UserPrompt):
        return "user_prompt"
    if isinstance(record, AssistantResponse):
        return "assistant_response"
    if isinstance(record, NamedLifecycleEvent | UnknownEvent):
        return record.name
    return None


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
