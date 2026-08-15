"""Builders for synthetic OTLP HTTP/JSON payloads."""

type JsonObject = dict[str, object]


def attr(key: str, value: object) -> JsonObject:
    return {"key": key, "value": any_value(value)}


def any_value(value: object) -> JsonObject:
    if isinstance(value, dict) and any(
        key in value
        for key in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue", "arrayValue", "kvlistValue")
    ):
        return value
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [any_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"kvlistValue": {"values": [attr(str(key), item) for key, item in value.items()]}}
    return {"stringValue": str(value)}


def log_record(
    *,
    event_name: str | None = None,
    event_name_field: str | None = None,
    body: object | None = None,
    attributes: dict[str, object] | None = None,
    time_unix_nano: str | int | None = "1000",
) -> JsonObject:
    record: JsonObject = {}
    if time_unix_nano is not None:
        record["timeUnixNano"] = time_unix_nano
    if event_name_field is not None:
        record["eventName"] = event_name_field
    if body is not None:
        record["body"] = any_value(body) if not isinstance(body, dict) else body
    attrs = dict(attributes or {})
    if event_name is not None:
        attrs.setdefault("event.name", event_name)
    if attrs:
        record["attributes"] = [attr(key, value) for key, value in attrs.items()]
    return record


def resource_logs(
    records: list[JsonObject],
    resource_attributes: dict[str, object] | None = None,
) -> JsonObject:
    resource = {"attributes": [attr(key, value) for key, value in (resource_attributes or {}).items()]}
    return {"resourceLogs": [{"resource": resource, "scopeLogs": [{"logRecords": records}]}]}


def number_point(
    *,
    value: int | float,
    attributes: dict[str, object] | None = None,
    start_time_unix_nano: str | int | None = "1",
    time_unix_nano: str | int | None = "2",
    as_string: bool = False,
) -> JsonObject:
    point: JsonObject = {
        "startTimeUnixNano": start_time_unix_nano,
        "timeUnixNano": time_unix_nano,
        "attributes": [attr(key, item) for key, item in (attributes or {}).items()],
    }
    if isinstance(value, float):
        point["asDouble"] = value
    elif as_string:
        point["asInt"] = str(value)
    else:
        point["asInt"] = value
    return point


def sum_metric(
    name: str,
    points: list[JsonObject],
    *,
    temporality: object = 1,
    unit: str = "",
) -> JsonObject:
    return {
        "name": name,
        "unit": unit,
        "sum": {"aggregationTemporality": temporality, "dataPoints": points},
    }


def gauge_metric(name: str, points: list[JsonObject], *, unit: str = "") -> JsonObject:
    return {"name": name, "unit": unit, "gauge": {"dataPoints": points}}


def histogram_metric(name: str, points: list[JsonObject] | None = None) -> JsonObject:
    return {"name": name, "histogram": {"dataPoints": points or [{}]}}


def resource_metrics(
    metrics: list[JsonObject],
    resource_attributes: dict[str, object] | None = None,
) -> JsonObject:
    resource = {"attributes": [attr(key, value) for key, value in (resource_attributes or {}).items()]}
    return {"resourceMetrics": [{"resource": resource, "scopeMetrics": [{"metrics": metrics}]}]}


def envelope(
    *,
    signal: str,
    payload: JsonObject,
    source: str = "claude-code",
    received_at: str = "2026-08-15T10:00:00+00:00",
    schema_version: int = 1,
) -> JsonObject:
    return {
        "schema_version": schema_version,
        "received_at": received_at,
        "source": source,
        "signal": signal,
        "payload": payload,
    }
