"""Allowlist normalizer for Claude Code OTLP records."""

from collections.abc import Iterable
from typing import Final

from coding_agent_performance.trace.cost import try_usd_to_micros
from coding_agent_performance.trace.otel import DecodedOtlp, OtlpLogRecord, OtlpMetricPoint, OtlpValue
from coding_agent_performance.trace.records import (
    ActivityMeasurement,
    AggregationTemporality,
    AssistantResponse,
    DomainRecord,
    MetricAttributes,
    ModelRequest,
    ModelRequestError,
    NamedLifecycleEvent,
    ToolExecution,
    UnknownEvent,
    UnknownMetric,
    UserPrompt,
)

_LIFECYCLE_EVENTS: Final = frozenset(
    {
        "api_refusal",
        "compaction",
        "subagent_completed",
        "tool_decision",
    }
)
_KNOWN_METRICS: Final = {
    "claude_code.session.count": (),
    "claude_code.lines_of_code.count": ("type", "model"),
    "claude_code.pull_request.count": (),
    "claude_code.commit.count": (),
    "claude_code.cost.usage": ("model", "query_source"),
    "claude_code.token.usage": ("type", "model", "query_source"),
    "claude_code.code_edit_tool.decision": ("tool_name", "decision", "language"),
    "claude_code.active_time.total": ("type",),
}


def normalize_decoded(decoded: DecodedOtlp) -> tuple[DomainRecord, ...]:
    records: list[DomainRecord] = []
    for log in decoded.logs:
        records.append(normalize_log(log))
    for point in decoded.metrics:
        records.append(normalize_metric(point))
    return tuple(records)


def normalize_logs(records: Iterable[OtlpLogRecord]) -> tuple[DomainRecord, ...]:
    return tuple(normalize_log(record) for record in records)


def normalize_log(record: OtlpLogRecord) -> DomainRecord:
    attrs = record.attributes
    session_id = _optional_str(attrs.get("session.id"))
    prompt_id = _optional_str(attrs.get("prompt.id"))
    sequence = _as_int(attrs.get("event.sequence"))
    match record.event_name:
        case "api_request":
            return _model_request(attrs, session_id, prompt_id, sequence)
        case "api_error":
            return ModelRequestError(
                session_id=session_id,
                prompt_id=prompt_id,
                model=_optional_str(attrs.get("model")),
                status_code=_as_int(attrs.get("status_code")),
                duration_ms=_as_int(attrs.get("duration_ms")),
                attempt_count=_as_int(attrs.get("attempt")),
                query_source=_optional_str(attrs.get("query_source")),
                event_sequence=sequence,
            )
        case "tool_result":
            return _tool_execution(attrs, session_id, prompt_id, sequence)
        case "user_prompt":
            return UserPrompt(
                session_id=session_id,
                prompt_id=prompt_id,
                prompt_length=_as_int(attrs.get("prompt_length")),
                event_sequence=sequence,
            )
        case "assistant_response":
            return AssistantResponse(
                session_id=session_id,
                prompt_id=prompt_id,
                model=_optional_str(attrs.get("model")),
                query_source=_optional_str(attrs.get("query_source")),
                response_length=_as_int(attrs.get("response_length")),
                event_sequence=sequence,
            )
        case name if name in _LIFECYCLE_EVENTS:
            return NamedLifecycleEvent(name=name, session_id=session_id, event_sequence=sequence)
        case name:
            return UnknownEvent(name=name or "unnamed", session_id=session_id, event_sequence=sequence)


def normalize_metric(point: OtlpMetricPoint) -> DomainRecord:
    allowed = _KNOWN_METRICS.get(point.name)
    if allowed is None:
        return UnknownMetric(name=point.name)
    return ActivityMeasurement(
        name=point.name,
        value=point.value,
        unit=point.unit,
        attributes=_allowed_attributes(point, allowed),
        start_time_unix_nano=point.start_time_unix_nano,
        time_unix_nano=point.time_unix_nano,
        aggregation_temporality=_metric_temporality(point.aggregation_temporality),
        kind=point.kind,
    )


def _model_request(
    attrs: dict[str, OtlpValue],
    session_id: str | None,
    prompt_id: str | None,
    sequence: int | None,
) -> ModelRequest:
    model = _optional_str(attrs.get("model")) or "unknown"
    input_tokens = _as_int(attrs.get("input_tokens"))
    output_tokens = _as_int(attrs.get("output_tokens"))
    cost_micros, has_cost = _cost_micros(attrs)
    return ModelRequest(
        session_id=session_id,
        prompt_id=prompt_id,
        model=model,
        query_source=_optional_str(attrs.get("query_source")),
        duration_ms=_as_int(attrs.get("duration_ms")),
        input_tokens=input_tokens or 0,
        output_tokens=output_tokens or 0,
        cache_read_tokens=_as_int(attrs.get("cache_read_tokens")) or 0,
        cache_creation_tokens=_as_int(attrs.get("cache_creation_tokens")) or 0,
        estimated_cost_usd_micros=cost_micros,
        event_sequence=sequence,
        has_input_tokens=input_tokens is not None,
        has_output_tokens=output_tokens is not None,
        has_estimated_cost_usd_micros=has_cost,
    )


def _tool_execution(
    attrs: dict[str, OtlpValue],
    session_id: str | None,
    prompt_id: str | None,
    sequence: int | None,
) -> ToolExecution:
    success = _as_bool(attrs.get("success"))
    return ToolExecution(
        session_id=session_id,
        prompt_id=prompt_id,
        tool_name=_optional_str(attrs.get("tool_name")) or "unknown",
        success=success is not False,
        duration_ms=_as_int(attrs.get("duration_ms")),
        input_size_bytes=_as_int(attrs.get("tool_input_size_bytes")),
        result_size_bytes=_as_int(attrs.get("tool_result_size_bytes")),
        error_type=_optional_str(attrs.get("error_type")),
        tool_use_id=_optional_str(attrs.get("tool_use_id")),
        event_sequence=sequence,
        success_valid=success is not None,
    )


def _cost_micros(attrs: dict[str, OtlpValue]) -> tuple[int, bool]:
    micros = _as_int(attrs.get("cost_usd_micros"))
    if micros is not None:
        return micros, True
    raw = attrs.get("cost_usd")
    if raw is None:
        return 0, False
    converted = try_usd_to_micros(raw)
    if converted is None:
        return 0, False
    return converted, True


def _allowed_attributes(point: OtlpMetricPoint, allowed: tuple[str, ...]) -> MetricAttributes:
    selected = ((key, value) for key in allowed if (value := _optional_str(point.attributes.get(key))) is not None)
    return tuple(sorted(selected))


def _metric_temporality(value: str | None) -> AggregationTemporality | None:
    if value == "delta" or value == "cumulative":
        return value
    return None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value:
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None
