from coding_agent_performance.trace.otel import (
    OtlpBytes,
    decode_any_value,
    decode_attributes,
    decode_otlp,
    normalize_event_name,
    normalize_temporality,
)
from tests.helpers.otlp import (
    attr,
    gauge_metric,
    histogram_metric,
    log_record,
    number_point,
    resource_logs,
    resource_metrics,
    sum_metric,
)


def test_any_value_types() -> None:
    assert decode_any_value({"stringValue": "hello"})[0] == "hello"
    assert decode_any_value({"boolValue": True})[0] is True
    assert decode_any_value({"intValue": 7})[0] == 7
    assert decode_any_value({"intValue": "42"})[0] == 42
    assert decode_any_value({"doubleValue": 1.5})[0] == 1.5
    bytes_value, unknown = decode_any_value({"bytesValue": "YWI="})
    assert isinstance(bytes_value, OtlpBytes)
    assert bytes_value.encoded == "YWI="
    assert unknown == 0
    array, _ = decode_any_value({"arrayValue": {"values": [{"intValue": "1"}, {"stringValue": "x"}]}})
    assert array == [1, "x"]
    kvlist, _ = decode_any_value({"kvlistValue": {"values": [attr("a", "b")]}})
    assert kvlist == {"a": "b"}


def test_unknown_any_value_is_counted_without_leaking() -> None:
    value, unknown = decode_any_value({"mysteryValue": "secret"})
    assert unknown == 1
    assert "secret" not in repr(value)


def test_resource_and_record_attribute_precedence() -> None:
    payload = resource_logs(
        [log_record(event_name="api_request", attributes={"model": "record-model", "only.record": "yes"})],
        resource_attributes={"model": "resource-model", "only.resource": "yes"},
    )
    decoded = decode_otlp("logs", payload)
    record = decoded.logs[0]
    assert record.attributes["model"] == "record-model"
    assert record.attributes["only.resource"] == "yes"
    assert record.attributes["only.record"] == "yes"


def test_event_name_from_attribute_and_normalization() -> None:
    payload = resource_logs([log_record(event_name="claude_code.api_request")])
    assert decode_otlp("logs", payload).logs[0].event_name == "api_request"
    assert normalize_event_name("api_request") == "api_request"


def test_event_name_from_event_name_field() -> None:
    payload = resource_logs([log_record(event_name_field="claude_code.tool_result")])
    assert decode_otlp("logs", payload).logs[0].event_name == "tool_result"


def test_event_name_from_textual_body() -> None:
    payload = resource_logs([log_record(body="claude_code.user_prompt")])
    record = decode_otlp("logs", payload).logs[0]
    assert record.event_name == "user_prompt"
    assert "body" not in record.attributes


def test_body_fallback_ignores_non_event_text() -> None:
    payload = resource_logs([log_record(body="not an event")])
    assert decode_otlp("logs", payload).logs[0].event_name is None


def test_sum_and_gauge_datapoints() -> None:
    payload = resource_metrics(
        [
            sum_metric(
                "claude_code.token.usage",
                [number_point(value=3, as_string=True, attributes={"type": "input"})],
                temporality="AGGREGATION_TEMPORALITY_DELTA",
                unit="tokens",
            ),
            gauge_metric(
                "claude_code.active_time.total", [number_point(value=1.25, attributes={"type": "user"})], unit="s"
            ),
        ]
    )
    decoded = decode_otlp("metrics", payload)
    assert decoded.metrics[0].kind == "sum"
    assert decoded.metrics[0].value == 3
    assert decoded.metrics[0].aggregation_temporality == "delta"
    assert decoded.metrics[1].kind == "gauge"
    assert decoded.metrics[1].value == 1.25


def test_as_double_and_as_int() -> None:
    payload = resource_metrics(
        [
            sum_metric("m", [number_point(value=2.5)], temporality=1),
            sum_metric("n", [number_point(value=9, as_string=True)], temporality=2),
        ]
    )
    values = [point.value for point in decode_otlp("metrics", payload).metrics]
    assert values == [2.5, 9]


def test_histogram_is_unsupported() -> None:
    payload = resource_metrics([histogram_metric("claude_code.fake.histogram", [{}, {}])])
    decoded = decode_otlp("metrics", payload)
    assert decoded.metrics == ()
    assert decoded.unsupported_metric_points == 2


def test_malformed_structures_are_skipped() -> None:
    decoded = decode_otlp(
        "logs",
        {"resourceLogs": [None, "x", {"scopeLogs": [None, {"logRecords": [None, 1]}]}]},
    )
    assert decoded.logs == ()
    metrics = decode_otlp("metrics", {"resourceMetrics": [{"scopeMetrics": [{"metrics": [None, {}]}]}]})
    assert metrics.metrics == ()


def test_unknown_signal_is_empty() -> None:
    assert decode_otlp("traces", {}).logs == ()


def test_invalid_any_value_shapes() -> None:
    assert decode_any_value(None)[1] == 1
    assert decode_any_value({"intValue": "nope"})[1] == 1
    assert decode_any_value({"doubleValue": True})[1] == 1
    assert decode_any_value({"doubleValue": "1.5"})[0] == 1.5
    assert decode_any_value({"bytesValue": 1})[1] == 1
    assert decode_any_value({"arrayValue": "bad"})[1] == 1
    assert decode_any_value({"kvlistValue": "bad"})[1] == 1
    assert decode_any_value({"stringValue": 1})[1] == 1
    assert decode_any_value({"boolValue": "true"})[1] == 1


def test_decode_attributes_skips_malformed_items() -> None:
    attrs, unknown = decode_attributes([None, {"key": ""}, {"key": "ok", "value": {"stringValue": "x"}}, "x"])
    assert attrs == {"ok": "x"}
    assert unknown == 0
    assert decode_attributes("nope")[0] == {}


def test_body_any_value_and_missing_metric_name() -> None:
    payload = resource_logs([{"body": {"stringValue": "claude_code.compaction"}, "timeUnixNano": "1"}])
    assert decode_otlp("logs", payload).logs[0].event_name == "compaction"
    metrics = decode_otlp("metrics", resource_metrics([{"sum": {"dataPoints": [number_point(value=1)]}}]))
    assert metrics.metrics == ()


def test_bad_as_double_and_non_dict_point() -> None:
    payload: dict[str, object] = {
        "resourceMetrics": [
            {
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "m",
                                "sum": {"aggregationTemporality": 1, "dataPoints": [{"asDouble": "nope"}, "x"]},
                            }
                        ]
                    }
                ]
            }
        ]
    }
    assert decode_otlp("metrics", payload).metrics == ()


def test_non_finite_double_values_are_unknown() -> None:
    for raw in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", "-Infinity"):
        value, unknown = decode_any_value({"doubleValue": raw})
        assert unknown == 1
        assert value is not raw


def test_non_finite_as_double_is_skipped() -> None:
    payload: dict[str, object] = {
        "resourceMetrics": [
            {
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "m",
                                "sum": {
                                    "aggregationTemporality": 1,
                                    "dataPoints": [{"asDouble": "Infinity"}, {"asDouble": float("nan")}],
                                },
                            }
                        ]
                    }
                ]
            }
        ]
    }
    assert decode_otlp("metrics", payload).metrics == ()


def test_temporality_names_and_numbers() -> None:
    assert normalize_temporality(1) == "delta"
    assert normalize_temporality(2) == "cumulative"
    assert normalize_temporality("DELTA") == "delta"
    assert normalize_temporality("CUMULATIVE") == "cumulative"
    assert normalize_temporality("nope") is None
