from coding_agent_performance.adapters.claude_code.normalizer import normalize_log, normalize_logs, normalize_metric
from coding_agent_performance.trace.otel import OtlpLogRecord, OtlpMetricPoint, OtlpValue
from coding_agent_performance.trace.records import (
    ActivityMeasurement,
    AssistantResponse,
    ModelRequest,
    ModelRequestError,
    NamedLifecycleEvent,
    ToolExecution,
    UnknownEvent,
    UnknownMetric,
    UserPrompt,
)
from tests.helpers.synthetic_capture import (
    BASH_COMMAND,
    EMAIL,
    ERROR_TEXT,
    PROMPT_1,
    PROMPT_TEXT,
    RESPONSE_TEXT,
    SESSION,
    WORKSPACE,
)


def _log(name: str, **attributes: OtlpValue) -> OtlpLogRecord:
    return OtlpLogRecord(time_unix_nano=1, event_name=name, attributes=attributes)


def test_normalizes_api_request() -> None:
    record = normalize_log(
        _log(
            "api_request",
            **{
                "session.id": SESSION,
                "prompt.id": PROMPT_1,
                "event.sequence": 2,
                "model": "claude-example",
                "query_source": "main",
                "duration_ms": 900,
                "input_tokens": 400,
                "output_tokens": 200,
                "cache_read_tokens": 300,
                "cache_creation_tokens": 50,
                "cost_usd_micros": 5000,
            },
        )
    )
    assert isinstance(record, ModelRequest)
    assert record.model == "claude-example"
    assert record.query_source == "main"
    assert record.duration_ms == 900
    assert record.input_tokens == 400
    assert record.estimated_cost_usd_micros == 5000
    assert record.has_input_tokens is True
    assert record.has_output_tokens is True
    assert record.has_estimated_cost_usd_micros is True
    assert record.session_id == SESSION
    assert not hasattr(record, "user.email")


def test_prefers_cost_micros_over_usd() -> None:
    record = normalize_log(
        _log("api_request", model="m", cost_usd_micros=12, cost_usd=9.99, input_tokens=1, output_tokens=0)
    )
    assert isinstance(record, ModelRequest)
    assert record.estimated_cost_usd_micros == 12


def test_non_finite_cost_usd_is_zero() -> None:
    infinite = normalize_log(_log("api_request", model="m", cost_usd=float("inf")))
    nan_text = normalize_log(_log("api_request", model="m", cost_usd="NaN"))
    assert isinstance(infinite, ModelRequest)
    assert infinite.estimated_cost_usd_micros == 0
    assert infinite.has_estimated_cost_usd_micros is False
    assert isinstance(nan_text, ModelRequest)
    assert nan_text.estimated_cost_usd_micros == 0
    assert nan_text.has_estimated_cost_usd_micros is False


def test_cost_fallback_uses_decimal() -> None:
    record = normalize_log(_log("api_request", model="m", cost_usd="0.012345"))
    assert isinstance(record, ModelRequest)
    assert record.estimated_cost_usd_micros == 12345


def test_api_error_does_not_keep_message() -> None:
    record = normalize_log(
        _log(
            "api_error",
            model="claude-example",
            status_code=500,
            duration_ms=10,
            attempt=3,
            query_source="main",
            error=ERROR_TEXT,
        )
    )
    assert isinstance(record, ModelRequestError)
    assert record.status_code == 500
    assert record.attempt_count == 3
    assert ERROR_TEXT not in repr(record)
    assert not hasattr(record, "error")


def test_tool_success_and_failure_drop_content() -> None:
    success = normalize_log(
        _log(
            "tool_result",
            tool_name="Bash",
            success="true",
            duration_ms=300,
            tool_input_size_bytes=200,
            tool_result_size_bytes=1000,
            tool_input={"command": BASH_COMMAND},
            tool_parameters=BASH_COMMAND,
        )
    )
    failure = normalize_log(
        _log(
            "tool_result",
            tool_name="Bash",
            success="false",
            error_type="ShellError",
            error=ERROR_TEXT,
            duration_ms=700,
        )
    )
    assert isinstance(success, ToolExecution)
    assert success.success is True
    assert success.success_valid is True
    assert success.input_size_bytes == 200
    assert BASH_COMMAND not in repr(success)
    assert isinstance(failure, ToolExecution)
    assert failure.success is False
    assert failure.success_valid is True
    assert failure.error_type == "ShellError"
    assert ERROR_TEXT not in repr(failure)


def test_prompt_and_response_drop_content() -> None:
    prompt = normalize_log(_log("user_prompt", prompt_length=42, prompt=PROMPT_TEXT, **{"session.id": SESSION}))
    response = normalize_log(
        _log("assistant_response", response_length=80, response=RESPONSE_TEXT, model="claude-example")
    )
    assert isinstance(prompt, UserPrompt)
    assert prompt.prompt_length == 42
    assert PROMPT_TEXT not in repr(prompt)
    assert isinstance(response, AssistantResponse)
    assert response.response_length == 80
    assert RESPONSE_TEXT not in repr(response)


def test_unknown_event_keeps_only_name() -> None:
    record = normalize_log(_log("weird_event", **{"user.email": EMAIL, "workspace.host_paths": WORKSPACE}))
    assert isinstance(record, UnknownEvent)
    assert record.name == "weird_event"
    assert EMAIL not in repr(record)
    assert WORKSPACE not in repr(record)


def test_metric_allowlist_drops_identity() -> None:
    record = normalize_metric(
        OtlpMetricPoint(
            name="claude_code.token.usage",
            unit="tokens",
            value=10,
            attributes={"type": "input", "model": "claude-example", "session.id": SESSION, "user.email": EMAIL},
            start_time_unix_nano=1,
            time_unix_nano=2,
            aggregation_temporality="delta",
            kind="sum",
        )
    )
    assert isinstance(record, ActivityMeasurement)
    assert record.attributes == (("model", "claude-example"), ("type", "input"))
    assert SESSION not in dict(record.attributes).values()


def test_normalize_logs_and_lifecycle_events() -> None:
    records = normalize_logs(
        [
            _log("compaction", **{"event.sequence": 1}),
            _log("api_refusal", **{"event.sequence": 2}),
            OtlpLogRecord(time_unix_nano=1, event_name=None, attributes={}),
        ]
    )
    assert isinstance(records[0], NamedLifecycleEvent)
    assert records[0].name == "compaction"
    assert isinstance(records[1], NamedLifecycleEvent)
    assert isinstance(records[2], UnknownEvent)
    assert records[2].name == "unnamed"


def test_extreme_cost_usd_is_zero() -> None:
    record = normalize_log(_log("api_request", model="m", cost_usd="1e999999"))
    assert isinstance(record, ModelRequest)
    assert record.estimated_cost_usd_micros == 0
    assert record.has_estimated_cost_usd_micros is False


def test_explicit_zero_usage_fields_remain_present() -> None:
    record = normalize_log(_log("api_request", model="m", input_tokens=0, output_tokens=0, cost_usd_micros=0))
    assert isinstance(record, ModelRequest)
    assert record.input_tokens == 0
    assert record.output_tokens == 0
    assert record.estimated_cost_usd_micros == 0
    assert record.has_input_tokens is True
    assert record.has_output_tokens is True
    assert record.has_estimated_cost_usd_micros is True


def test_partial_api_usage_fields_preserve_independent_presence() -> None:
    record = normalize_log(_log("api_request", model="m", input_tokens=4, cost_usd="0.000012"))
    assert isinstance(record, ModelRequest)
    assert record.input_tokens == 4
    assert record.output_tokens == 0
    assert record.estimated_cost_usd_micros == 12
    assert record.has_input_tokens is True
    assert record.has_output_tokens is False
    assert record.has_estimated_cost_usd_micros is True


def test_invalid_input_and_output_tokens_are_absent() -> None:
    record = normalize_log(_log("api_request", model="m", input_tokens="n/a", output_tokens=False))
    assert isinstance(record, ModelRequest)
    assert record.input_tokens == 0
    assert record.output_tokens == 0
    assert record.has_input_tokens is False
    assert record.has_output_tokens is False


def test_cost_and_coercion_edges() -> None:
    missing = normalize_log(_log("api_request", model="m"))
    invalid = normalize_log(_log("api_request", model="m", cost_usd="not-a-number"))
    assert isinstance(missing, ModelRequest)
    assert missing.estimated_cost_usd_micros == 0
    assert missing.has_estimated_cost_usd_micros is False
    assert missing.has_input_tokens is False
    assert missing.has_output_tokens is False
    assert isinstance(invalid, ModelRequest)
    assert invalid.estimated_cost_usd_micros == 0
    assert invalid.has_estimated_cost_usd_micros is False
    typed = normalize_log(
        _log(
            "tool_result",
            tool_name="Read",
            success=True,
            duration_ms=10.0,
            tool_input_size_bytes="12",
            tool_result_size_bytes=False,
        )
    )
    assert isinstance(typed, ToolExecution)
    assert typed.success is True
    assert typed.success_valid is True
    assert typed.duration_ms == 10
    assert typed.input_size_bytes == 12
    assert typed.result_size_bytes is None
    failed = normalize_log(_log("tool_result", tool_name="Read", success="false"))
    assert isinstance(failed, ToolExecution)
    assert failed.success is False
    assert failed.success_valid is True
    unknown_success = normalize_log(_log("tool_result", tool_name="Read", success="maybe"))
    assert isinstance(unknown_success, ToolExecution)
    assert unknown_success.success is True
    assert unknown_success.success_valid is False
    missing_success = normalize_log(_log("tool_result", tool_name="Read"))
    assert isinstance(missing_success, ToolExecution)
    assert missing_success.success is True
    assert missing_success.success_valid is False


def test_unknown_metric() -> None:
    record = normalize_metric(
        OtlpMetricPoint(
            name="custom.unknown.metric",
            unit="",
            value=1,
            attributes={"session.id": SESSION},
            start_time_unix_nano=1,
            time_unix_nano=2,
            aggregation_temporality="delta",
            kind="sum",
        )
    )
    assert isinstance(record, UnknownMetric)
    assert record.name == "custom.unknown.metric"
