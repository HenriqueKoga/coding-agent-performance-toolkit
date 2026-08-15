"""OTLP HTTP/JSON decoder.

This module understands OpenTelemetry JSON encoding only. It does not
know Claude Code event names or any other vendor-specific schema.
"""

import math
from dataclasses import dataclass
from typing import Final, Literal

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type OtlpValue = JsonValue | OtlpBytes | list[OtlpValue] | dict[str, OtlpValue]

_ANY_VALUE_KEYS: Final = (
    "stringValue",
    "boolValue",
    "intValue",
    "doubleValue",
    "bytesValue",
    "arrayValue",
    "kvlistValue",
)
_UNSUPPORTED_METRIC_KEYS: Final = ("histogram", "exponentialHistogram", "summary")
_CLAUDE_CODE_PREFIX: Final = "claude_code."


@dataclass(frozen=True, slots=True)
class OtlpBytes:
    """Opaque OTLP bytes payload. Not decoded as text."""

    encoded: str


@dataclass(frozen=True, slots=True)
class OtlpLogRecord:
    time_unix_nano: int | None
    event_name: str | None
    attributes: dict[str, OtlpValue]


@dataclass(frozen=True, slots=True)
class OtlpMetricPoint:
    name: str
    unit: str
    value: int | float
    attributes: dict[str, OtlpValue]
    start_time_unix_nano: int | None
    time_unix_nano: int | None
    aggregation_temporality: str | None
    kind: Literal["sum", "gauge"]


@dataclass(frozen=True, slots=True)
class DecodedOtlp:
    logs: tuple[OtlpLogRecord, ...]
    metrics: tuple[OtlpMetricPoint, ...]
    unsupported_metric_points: int
    unknown_value_count: int


class _UnknownValue:
    pass


_UNKNOWN = _UnknownValue()


def decode_otlp(signal: str, payload: dict[str, object]) -> DecodedOtlp:
    unknown = 0
    if signal == "logs":
        logs, unknown = _decode_resource_logs(payload.get("resourceLogs"))
        return DecodedOtlp(logs=logs, metrics=(), unsupported_metric_points=0, unknown_value_count=unknown)
    if signal == "metrics":
        metrics, unsupported, unknown = _decode_resource_metrics(payload.get("resourceMetrics"))
        return DecodedOtlp(logs=(), metrics=metrics, unsupported_metric_points=unsupported, unknown_value_count=unknown)
    return DecodedOtlp(logs=(), metrics=(), unsupported_metric_points=0, unknown_value_count=0)


def decode_any_value(value: object) -> tuple[OtlpValue | _UnknownValue, int]:
    if not isinstance(value, dict):
        return _UNKNOWN, 1
    present = [key for key in _ANY_VALUE_KEYS if key in value]
    if not present:
        return _UNKNOWN, 1
    kind = present[0]
    raw = value.get(kind)
    if kind == "stringValue":
        return (raw, 0) if isinstance(raw, str) else (_UNKNOWN, 1)
    if kind == "boolValue":
        return (raw, 0) if isinstance(raw, bool) else (_UNKNOWN, 1)
    if kind == "intValue":
        parsed = _parse_int(raw)
        return (parsed, 0) if parsed is not None else (_UNKNOWN, 1)
    if kind == "doubleValue":
        parsed = _parse_finite_float(raw)
        return (parsed, 0) if parsed is not None else (_UNKNOWN, 1)
    if kind == "bytesValue":
        return (OtlpBytes(encoded=raw), 0) if isinstance(raw, str) else (_UNKNOWN, 1)
    if kind == "arrayValue":
        return _decode_array(raw)
    return _decode_kvlist(raw)


def _decode_array(raw: object) -> tuple[OtlpValue | _UnknownValue, int]:
    values = raw.get("values") if isinstance(raw, dict) else None
    if not isinstance(values, list):
        return _UNKNOWN, 1
    decoded: list[OtlpValue] = []
    unknown = 0
    for item in values:
        value, count = decode_any_value(item)
        unknown += count
        if not isinstance(value, _UnknownValue):
            decoded.append(value)
    return decoded, unknown


def _decode_kvlist(raw: object) -> tuple[OtlpValue | _UnknownValue, int]:
    values = raw.get("values") if isinstance(raw, dict) else None
    if not isinstance(values, list):
        return _UNKNOWN, 1
    decoded, unknown = decode_attributes(values)
    return decoded, unknown


def decode_attributes(items: object) -> tuple[dict[str, OtlpValue], int]:
    result: dict[str, OtlpValue] = {}
    unknown = 0
    if not isinstance(items, list):
        return result, 0
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not isinstance(key, str) or not key:
            continue
        value, count = decode_any_value(item.get("value"))
        unknown += count
        if not isinstance(value, _UnknownValue):
            result[key] = value
    return result, unknown


def _decode_resource_logs(resource_logs: object) -> tuple[tuple[OtlpLogRecord, ...], int]:
    records: list[OtlpLogRecord] = []
    unknown = 0
    if not isinstance(resource_logs, list):
        return (), 0
    for resource_log in resource_logs:
        if not isinstance(resource_log, dict):
            continue
        resource_attrs, count = _resource_attributes(resource_log.get("resource"))
        unknown += count
        scope_logs = resource_log.get("scopeLogs")
        if not isinstance(scope_logs, list):
            continue
        for scope_log in scope_logs:
            if not isinstance(scope_log, dict):
                continue
            log_records = scope_log.get("logRecords")
            if not isinstance(log_records, list):
                continue
            for item in log_records:
                record, count = _decode_log_record(item, resource_attrs)
                unknown += count
                if record is not None:
                    records.append(record)
    return tuple(records), unknown


def _decode_log_record(item: object, resource_attrs: dict[str, OtlpValue]) -> tuple[OtlpLogRecord | None, int]:
    if not isinstance(item, dict):
        return None, 0
    record_attrs, unknown = decode_attributes(item.get("attributes"))
    attributes = {**resource_attrs, **record_attrs}
    event_name = _event_name(item, attributes)
    return (
        OtlpLogRecord(
            time_unix_nano=_parse_int(item.get("timeUnixNano") or item.get("observedTimeUnixNano")),
            event_name=event_name,
            attributes=attributes,
        ),
        unknown,
    )


def _event_name(item: dict[str, object], attributes: dict[str, OtlpValue]) -> str | None:
    raw = attributes.get("event.name")
    if isinstance(raw, str) and raw:
        return normalize_event_name(raw)
    field = item.get("eventName")
    if isinstance(field, str) and field:
        return normalize_event_name(field)
    body_text = _textual_body(item.get("body"))
    if body_text is not None and body_text.startswith(_CLAUDE_CODE_PREFIX) and body_text != _CLAUDE_CODE_PREFIX:
        return normalize_event_name(body_text)
    return None


def normalize_event_name(name: str) -> str:
    if name.startswith(_CLAUDE_CODE_PREFIX):
        return name.removeprefix(_CLAUDE_CODE_PREFIX)
    return name


def _textual_body(body: object) -> str | None:
    if isinstance(body, str) and body:
        return body
    if not isinstance(body, dict):
        return None
    value, _unknown = decode_any_value(body)
    return value if isinstance(value, str) and value else None


def _decode_resource_metrics(
    resource_metrics: object,
) -> tuple[tuple[OtlpMetricPoint, ...], int, int]:
    points: list[OtlpMetricPoint] = []
    unsupported = 0
    unknown = 0
    if not isinstance(resource_metrics, list):
        return (), 0, 0
    for resource_metric in resource_metrics:
        if not isinstance(resource_metric, dict):
            continue
        resource_attrs, count = _resource_attributes(resource_metric.get("resource"))
        unknown += count
        scope_metrics = resource_metric.get("scopeMetrics")
        if not isinstance(scope_metrics, list):
            continue
        for scope_metric in scope_metrics:
            if not isinstance(scope_metric, dict):
                continue
            metrics = scope_metric.get("metrics")
            if not isinstance(metrics, list):
                continue
            for metric in metrics:
                decoded, skipped, count = _decode_metric(metric, resource_attrs)
                points.extend(decoded)
                unsupported += skipped
                unknown += count
    return tuple(points), unsupported, unknown


def _decode_metric(
    metric: object,
    resource_attrs: dict[str, OtlpValue],
) -> tuple[list[OtlpMetricPoint], int, int]:
    if not isinstance(metric, dict):
        return [], 0, 0
    name = metric.get("name")
    if not isinstance(name, str) or not name:
        return [], 0, 0
    unit = metric.get("unit")
    unit_text = unit if isinstance(unit, str) else ""
    unsupported = 0
    for key in _UNSUPPORTED_METRIC_KEYS:
        payload = metric.get(key)
        if isinstance(payload, dict):
            data_points = payload.get("dataPoints")
            unsupported += len(data_points) if isinstance(data_points, list) else 1
    points: list[OtlpMetricPoint] = []
    unknown = 0
    for kind, key in (("sum", "sum"), ("gauge", "gauge")):
        payload = metric.get(key)
        if not isinstance(payload, dict):
            continue
        temporality = normalize_temporality(payload.get("aggregationTemporality")) if kind == "sum" else None
        data_points = payload.get("dataPoints")
        if not isinstance(data_points, list):
            continue
        for item in data_points:
            point, count = _decode_data_point(item, name, unit_text, kind, temporality, resource_attrs)
            unknown += count
            if point is not None:
                points.append(point)
    return points, unsupported, unknown


def _decode_data_point(
    item: object,
    name: str,
    unit: str,
    kind: Literal["sum", "gauge"],
    temporality: str | None,
    resource_attrs: dict[str, OtlpValue],
) -> tuple[OtlpMetricPoint | None, int]:
    if not isinstance(item, dict):
        return None, 0
    value = _number_point_value(item)
    if value is None:
        return None, 0
    attributes, unknown = decode_attributes(item.get("attributes"))
    merged = {**resource_attrs, **attributes}
    return (
        OtlpMetricPoint(
            name=name,
            unit=unit,
            value=value,
            attributes=merged,
            start_time_unix_nano=_parse_int(item.get("startTimeUnixNano")),
            time_unix_nano=_parse_int(item.get("timeUnixNano")),
            aggregation_temporality=temporality,
            kind=kind,
        ),
        unknown,
    )


def _number_point_value(item: dict[str, object]) -> int | float | None:
    if "asInt" in item:
        return _parse_int(item.get("asInt"))
    if "asDouble" in item:
        return _parse_finite_float(item.get("asDouble"))
    return None


def _parse_finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if isinstance(value, str) and value:
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def normalize_temporality(value: object) -> str | None:
    if value in {1, "1", "DELTA", "AGGREGATION_TEMPORALITY_DELTA"}:
        return "delta"
    if value in {2, "2", "CUMULATIVE", "AGGREGATION_TEMPORALITY_CUMULATIVE"}:
        return "cumulative"
    if isinstance(value, str):
        upper = value.upper()
        if upper.endswith("DELTA") or upper == "DELTA":
            return "delta"
        if upper.endswith("CUMULATIVE") or upper == "CUMULATIVE":
            return "cumulative"
    return None


def _resource_attributes(resource: object) -> tuple[dict[str, OtlpValue], int]:
    if not isinstance(resource, dict):
        return {}, 0
    return decode_attributes(resource.get("attributes"))


def _parse_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value:
        try:
            return int(value)
        except ValueError:
            return None
    return None
