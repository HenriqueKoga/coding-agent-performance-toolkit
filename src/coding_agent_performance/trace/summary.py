"""Incremental aggregation of normalized telemetry into a summary DTO."""

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Literal

from coding_agent_performance.adapters.claude_code.normalizer import normalize_decoded
from coding_agent_performance.trace.capture import CaptureEnvelope, CaptureError, CaptureReader
from coding_agent_performance.trace.model import (
    ActivityMeasurement,
    AssistantResponse,
    DomainRecord,
    ModelRequest,
    ModelRequestError,
    NamedLifecycleEvent,
    ToolExecution,
    UnknownEvent,
    UnknownMetric,
    UserPrompt,
)
from coding_agent_performance.trace.otel import decode_otlp

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
    usage_source: Literal["api_request_events", "otel_metrics", "none"]
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
class ActivityStats:
    active_time_seconds: dict[str, float]
    lines_of_code: dict[str, int]
    commits: int
    pull_requests: int
    code_edit_decisions: dict[str, int]


@dataclass(frozen=True, slots=True)
class CoverageStats:
    log_records: int
    metric_points: int
    duplicate_log_records: int
    duplicate_metric_points: int
    unsupported_metric_points: int
    unknown_otlp_values: int
    unknown_events: dict[str, int]
    unknown_metrics: dict[str, int]
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

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "capture": {
                "source": self.capture.source,
                "file": self.capture.file,
                "envelopes": self.capture.envelopes,
                "log_batches": self.capture.log_batches,
                "metric_batches": self.capture.metric_batches,
                "first_received_at": self.capture.first_received_at,
                "last_received_at": self.capture.last_received_at,
            },
            "sessions": {
                "count": self.sessions.count,
                "prompts": self.sessions.prompts,
                "assistant_responses": self.sessions.assistant_responses,
                "compactions": self.sessions.compactions,
                "subagents_completed": self.sessions.subagents_completed,
            },
            "model_usage": {
                "usage_source": self.model_usage.usage_source,
                "requests": self.model_usage.requests,
                "errors": self.model_usage.errors,
                "refusals": self.model_usage.refusals,
                "estimated_cost_usd_micros": self.model_usage.estimated_cost_usd_micros,
                "tokens": {
                    "input": self.model_usage.tokens.input,
                    "output": self.model_usage.tokens.output,
                    "cache_read": self.model_usage.tokens.cache_read,
                    "cache_creation": self.model_usage.tokens.cache_creation,
                },
                "duration_ms": {
                    "total": self.model_usage.duration_ms.total,
                    "average": self.model_usage.duration_ms.average,
                    "p50": self.model_usage.duration_ms.p50,
                    "p95": self.model_usage.duration_ms.p95,
                },
                "by_model": [
                    {
                        "model": row.model,
                        "requests": row.requests,
                        "estimated_cost_usd_micros": row.estimated_cost_usd_micros,
                        "input_tokens": row.input_tokens,
                        "output_tokens": row.output_tokens,
                        "cache_read_tokens": row.cache_read_tokens,
                        "cache_creation_tokens": row.cache_creation_tokens,
                    }
                    for row in self.model_usage.by_model
                ],
                "by_query_source": [
                    {
                        "query_source": row.query_source,
                        "requests": row.requests,
                        "estimated_cost_usd_micros": row.estimated_cost_usd_micros,
                    }
                    for row in self.model_usage.by_query_source
                ],
            },
            "tools": {
                "calls": self.tools.calls,
                "successes": self.tools.successes,
                "failures": self.tools.failures,
                "input_bytes": self.tools.input_bytes,
                "result_bytes": self.tools.result_bytes,
                "duration_ms": {
                    "total": self.tools.duration_ms.total,
                    "average": self.tools.duration_ms.average,
                    "p50": self.tools.duration_ms.p50,
                    "p95": self.tools.duration_ms.p95,
                },
                "by_name": [
                    {
                        "name": row.name,
                        "calls": row.calls,
                        "successes": row.successes,
                        "failures": row.failures,
                        "success_rate": row.success_rate,
                        "duration_ms_total": row.duration_ms_total,
                        "duration_ms_average": row.duration_ms_average,
                        "input_bytes": row.input_bytes,
                        "result_bytes": row.result_bytes,
                    }
                    for row in self.tools.by_name
                ],
            },
            "activity": {
                "active_time_seconds": {
                    "user": self.activity.active_time_seconds.get("user", 0.0),
                    "cli": self.activity.active_time_seconds.get("cli", 0.0),
                },
                "lines_of_code": {
                    "added": self.activity.lines_of_code.get("added", 0),
                    "removed": self.activity.lines_of_code.get("removed", 0),
                },
                "commits": self.activity.commits,
                "pull_requests": self.activity.pull_requests,
                "code_edit_decisions": {
                    "accepted": self.activity.code_edit_decisions.get("accepted", 0),
                    "rejected": self.activity.code_edit_decisions.get("rejected", 0),
                },
            },
            "coverage": {
                "log_records": self.coverage.log_records,
                "metric_points": self.coverage.metric_points,
                "duplicate_log_records": self.coverage.duplicate_log_records,
                "duplicate_metric_points": self.coverage.duplicate_metric_points,
                "unsupported_metric_points": self.coverage.unsupported_metric_points,
                "unknown_otlp_values": self.coverage.unknown_otlp_values,
                "unknown_events": dict(sorted(self.coverage.unknown_events.items())),
                "unknown_metrics": dict(sorted(self.coverage.unknown_metrics.items())),
                "warnings": list(self.coverage.warnings),
            },
        }


@dataclass
class _ModelBucket:
    requests: int = 0
    estimated_cost_usd_micros: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class _QueryBucket:
    requests: int = 0
    estimated_cost_usd_micros: int = 0


@dataclass
class _ToolBucket:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    duration_ms_total: int = 0
    duration_count: int = 0
    input_bytes: int = 0
    result_bytes: int = 0


@dataclass
class _Series:
    kind: str
    temporality: str | None
    latest_time: int | None = None
    latest_value: int | float = 0
    delta_total: int | float = 0


type _SeriesKey = tuple[str, tuple[tuple[str, str], ...], int | None]


@dataclass
class IncrementalSummarizer:
    filename: str
    source: str | None = None
    _envelopes: int = 0
    _log_batches: int = 0
    _metric_batches: int = 0
    _first_received_at: datetime | None = None
    _last_received_at: datetime | None = None
    _session_ids: set[str] = field(default_factory=set)
    _seen_logs: set[tuple[str, int, str]] = field(default_factory=set)
    _seen_points: set[tuple[_SeriesKey, int]] = field(default_factory=set)
    _series: dict[_SeriesKey, _Series] = field(default_factory=dict)
    _prompts: int = 0
    _assistant_responses: int = 0
    _compactions: int = 0
    _subagents_completed: int = 0
    _requests: int = 0
    _errors: int = 0
    _refusals: int = 0
    _event_cost: int = 0
    _event_tokens: TokenTotals = field(default_factory=lambda: TokenTotals(0, 0, 0, 0))
    _request_durations: list[int] = field(default_factory=list)
    _by_model: dict[str, _ModelBucket] = field(default_factory=dict)
    _by_query: dict[str, _QueryBucket] = field(default_factory=dict)
    _tool_calls: int = 0
    _tool_successes: int = 0
    _tool_failures: int = 0
    _tool_input_bytes: int = 0
    _tool_result_bytes: int = 0
    _tool_durations: list[int] = field(default_factory=list)
    _tools: dict[str, _ToolBucket] = field(default_factory=dict)
    _log_records: int = 0
    _metric_points: int = 0
    _duplicate_logs: int = 0
    _duplicate_points: int = 0
    _unsupported: int = 0
    _unknown_otlp_values: int = 0
    _unknown_events: dict[str, int] = field(default_factory=dict)
    _unknown_metrics: dict[str, int] = field(default_factory=dict)
    _warnings: list[str] = field(default_factory=list)
    _temporality_warned: bool = False

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
        self._envelopes += 1
        self.source = envelope.source
        if envelope.signal == "logs":
            self._log_batches += 1
        else:
            self._metric_batches += 1
        if self._first_received_at is None or envelope.received_at < self._first_received_at:
            self._first_received_at = envelope.received_at
        if self._last_received_at is None or envelope.received_at > self._last_received_at:
            self._last_received_at = envelope.received_at
        self._log_records += log_count
        self._metric_points += metric_count
        self._unsupported += unsupported
        self._unknown_otlp_values += unknown_otlp_values
        for record in records:
            self._ingest(record)

    def finish(self, path: Path) -> TraceSummary:
        if self._log_records == 0 and self._metric_points == 0 and self._unsupported == 0:
            raise CaptureError(path, "no recognized telemetry")
        usage = self._model_usage()
        return TraceSummary(
            schema_version=SUMMARY_SCHEMA_VERSION,
            capture=CaptureInfo(
                source=self.source or "unknown",
                file=self.filename,
                envelopes=self._envelopes,
                log_batches=self._log_batches,
                metric_batches=self._metric_batches,
                first_received_at=_isoformat(self._first_received_at),
                last_received_at=_isoformat(self._last_received_at),
            ),
            sessions=SessionStats(
                count=self._session_count(),
                prompts=self._prompts,
                assistant_responses=self._assistant_responses,
                compactions=self._compactions,
                subagents_completed=self._subagents_completed,
            ),
            model_usage=usage,
            tools=self._tool_stats(),
            activity=self._activity_stats(),
            coverage=CoverageStats(
                log_records=self._log_records,
                metric_points=self._metric_points,
                duplicate_log_records=self._duplicate_logs,
                duplicate_metric_points=self._duplicate_points,
                unsupported_metric_points=self._unsupported,
                unknown_otlp_values=self._unknown_otlp_values,
                unknown_events=dict(sorted(self._unknown_events.items())),
                unknown_metrics=dict(sorted(self._unknown_metrics.items())),
                warnings=tuple(self._warnings),
            ),
        )

    def _ingest(self, record: DomainRecord) -> None:
        if isinstance(record, ActivityMeasurement):
            self._ingest_measurement(record)
            return
        if isinstance(record, UnknownMetric):
            self._unknown_metrics[record.name] = self._unknown_metrics.get(record.name, 0) + 1
            return
        identity = _log_identity(record)
        if identity is not None:
            if identity in self._seen_logs:
                self._duplicate_logs += 1
                return
            self._seen_logs.add(identity)
        session_id = getattr(record, "session_id", None)
        if isinstance(session_id, str) and session_id:
            self._session_ids.add(session_id)
        if isinstance(record, ModelRequest):
            self._ingest_request(record)
        elif isinstance(record, ModelRequestError):
            self._errors += 1
        elif isinstance(record, ToolExecution):
            self._ingest_tool(record)
        elif isinstance(record, UserPrompt):
            self._prompts += 1
        elif isinstance(record, AssistantResponse):
            self._assistant_responses += 1
        elif isinstance(record, NamedLifecycleEvent):
            if record.name == "api_refusal":
                self._refusals += 1
            elif record.name == "compaction":
                self._compactions += 1
            elif record.name == "subagent_completed":
                self._subagents_completed += 1
        elif isinstance(record, UnknownEvent):
            self._unknown_events[record.name] = self._unknown_events.get(record.name, 0) + 1

    def _ingest_request(self, record: ModelRequest) -> None:
        self._requests += 1
        self._event_cost += record.estimated_cost_usd_micros
        self._event_tokens = TokenTotals(
            input=self._event_tokens.input + record.input_tokens,
            output=self._event_tokens.output + record.output_tokens,
            cache_read=self._event_tokens.cache_read + record.cache_read_tokens,
            cache_creation=self._event_tokens.cache_creation + record.cache_creation_tokens,
        )
        if record.duration_ms is not None:
            self._request_durations.append(record.duration_ms)
        bucket = self._by_model.setdefault(record.model, _ModelBucket())
        bucket.requests += 1
        bucket.estimated_cost_usd_micros += record.estimated_cost_usd_micros
        bucket.input_tokens += record.input_tokens
        bucket.output_tokens += record.output_tokens
        bucket.cache_read_tokens += record.cache_read_tokens
        bucket.cache_creation_tokens += record.cache_creation_tokens
        if record.query_source:
            query = self._by_query.setdefault(record.query_source, _QueryBucket())
            query.requests += 1
            query.estimated_cost_usd_micros += record.estimated_cost_usd_micros

    def _ingest_tool(self, record: ToolExecution) -> None:
        self._tool_calls += 1
        if record.success:
            self._tool_successes += 1
        else:
            self._tool_failures += 1
        input_bytes = record.input_size_bytes or 0
        result_bytes = record.result_size_bytes or 0
        self._tool_input_bytes += input_bytes
        self._tool_result_bytes += result_bytes
        bucket = self._tools.setdefault(record.tool_name, _ToolBucket())
        bucket.calls += 1
        if record.success:
            bucket.successes += 1
        else:
            bucket.failures += 1
        if record.duration_ms is not None:
            self._tool_durations.append(record.duration_ms)
            bucket.duration_ms_total += record.duration_ms
            bucket.duration_count += 1
        bucket.input_bytes += input_bytes
        bucket.result_bytes += result_bytes

    def _ingest_measurement(self, record: ActivityMeasurement) -> None:
        key = (record.name, tuple(sorted(record.attributes.items())), record.start_time_unix_nano)
        if record.time_unix_nano is not None:
            point_id = (key, record.time_unix_nano)
            if point_id in self._seen_points:
                self._duplicate_points += 1
                return
            self._seen_points.add(point_id)
        if record.kind == "sum" and record.aggregation_temporality is None:
            self._warn_temporality()
        series = self._series.get(key)
        if series is None:
            series = _Series(kind=record.kind, temporality=record.aggregation_temporality)
            self._series[key] = series
        if record.kind == "sum" and record.aggregation_temporality == "delta":
            series.delta_total = _add_number(series.delta_total, record.value)
        if _is_newer(record.time_unix_nano, series.latest_time):
            series.latest_time = record.time_unix_nano
            series.latest_value = record.value

    def _warn_temporality(self) -> None:
        if self._temporality_warned:
            return
        self._warnings.append("missing or unknown aggregation temporality; using latest datapoint per series")
        self._temporality_warned = True

    def _session_count(self) -> int:
        if self._session_ids:
            return len(self._session_ids)
        return int(self._metric_total("claude_code.session.count"))

    def _model_usage(self) -> ModelUsage:
        if self._requests > 0:
            return ModelUsage(
                usage_source="api_request_events",
                requests=self._requests,
                errors=self._errors,
                refusals=self._refusals,
                estimated_cost_usd_micros=self._event_cost,
                tokens=self._event_tokens,
                duration_ms=duration_stats(self._request_durations),
                by_model=self._event_model_rows(),
                by_query_source=self._event_query_rows(),
            )
        tokens, cost, by_model, by_query = self._metric_usage()
        has_usage_metrics = any(key[0] in _USAGE_METRICS for key in self._series)
        return ModelUsage(
            usage_source="otel_metrics" if has_usage_metrics else "none",
            requests=0,
            errors=self._errors,
            refusals=self._refusals,
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
            for name, bucket in self._by_model.items()
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
            for name, bucket in self._by_query.items()
        ]
        rows.sort(key=lambda row: row.query_source)
        return tuple(rows)

    def _metric_usage(self) -> tuple[TokenTotals, int, tuple[ModelBreakdown, ...], tuple[QuerySourceBreakdown, ...]]:
        tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        models: dict[str, _ModelBucket] = {}
        queries: dict[str, _QueryBucket] = {}
        cost = 0
        for key, series in self._series.items():
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
                    field_name = _token_field(token_type)
                    setattr(bucket, field_name, getattr(bucket, field_name) + amount)
                query = attr_map.get("query_source")
                if query:
                    queries.setdefault(query, _QueryBucket())
            elif name == "claude_code.cost.usage":
                micros = _usd_to_micros(value)
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
        return TokenTotals(**tokens), cost, by_model, by_query

    def _tool_stats(self) -> ToolStats:
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
            for name, bucket in self._tools.items()
        ]
        rows.sort(key=lambda row: row.name)
        return ToolStats(
            calls=self._tool_calls,
            successes=self._tool_successes,
            failures=self._tool_failures,
            input_bytes=self._tool_input_bytes,
            result_bytes=self._tool_result_bytes,
            duration_ms=duration_stats(self._tool_durations),
            by_name=tuple(rows),
        )

    def _activity_stats(self) -> ActivityStats:
        active = {"user": 0.0, "cli": 0.0}
        lines = {"added": 0, "removed": 0}
        decisions = {"accepted": 0, "rejected": 0}
        commits = 0
        pull_requests = 0
        for key, series in self._series.items():
            name, attrs, _start = key
            if name in _USAGE_METRICS:
                continue
            attr_map = dict(attrs)
            value = _resolved_value(series)
            if name == "claude_code.active_time.total":
                kind = attr_map.get("type")
                if kind in active:
                    active[kind] += float(value)
            elif name == "claude_code.lines_of_code.count":
                kind = attr_map.get("type")
                if kind in lines:
                    lines[kind] += int(value)
            elif name == "claude_code.commit.count":
                commits += int(value)
            elif name == "claude_code.pull_request.count":
                pull_requests += int(value)
            elif name == "claude_code.code_edit_tool.decision":
                decision = attr_map.get("decision")
                if decision == "accept":
                    decisions["accepted"] += int(value)
                elif decision == "reject":
                    decisions["rejected"] += int(value)
        return ActivityStats(
            active_time_seconds=active,
            lines_of_code=lines,
            commits=commits,
            pull_requests=pull_requests,
            code_edit_decisions=decisions,
        )

    def _metric_total(self, name: str) -> int | float:
        total: int | float = 0
        for key, series in self._series.items():
            if key[0] == name:
                total = _add_number(total, _resolved_value(series))
        return total


def summarize_capture(path: Path) -> TraceSummary:
    reader = CaptureReader(path)
    summarizer = IncrementalSummarizer(filename=path.name)
    for envelope in reader:
        decoded = decode_otlp(envelope.signal, envelope.payload)
        records = normalize_decoded(decoded)
        summarizer.add(
            envelope,
            records,
            log_count=len(decoded.logs),
            metric_count=len(decoded.metrics),
            unsupported=decoded.unsupported_metric_points,
            unknown_otlp_values=decoded.unknown_value_count,
        )
    return summarizer.finish(path)


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


def _usd_to_micros(value: int | float) -> int:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return 0
    if not amount.is_finite():
        return 0
    return int((amount * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_EVEN))


def _token_field(token_type: str) -> str:
    return {
        "input": "input_tokens",
        "output": "output_tokens",
        "cache_read": "cache_read_tokens",
        "cache_creation": "cache_creation_tokens",
    }[token_type]


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
