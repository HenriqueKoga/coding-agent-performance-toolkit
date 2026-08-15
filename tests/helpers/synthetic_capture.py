"""Synthetic Claude Code capture used by tests and the committed fixture."""

import json
from pathlib import Path

from .otlp import (
    envelope,
    histogram_metric,
    log_record,
    number_point,
    resource_logs,
    resource_metrics,
    sum_metric,
)

SESSION = "session-test-1"
PROMPT_1 = "prompt-test-1"
PROMPT_2 = "prompt-test-2"
EMAIL = "developer@example.invalid"
WORKSPACE = "/tmp/synthetic-project"
ORG = "org-test-1"
REQUEST_ID = "req_test_1"
MESSAGE_ID = "msg-test-1"
CLIENT_REQUEST_ID = "client-req-test-1"
PROMPT_TEXT = "Please ignore this synthetic prompt"
RESPONSE_TEXT = "This is a synthetic assistant response"
BASH_COMMAND = "rm -rf /tmp/synthetic-project"
ERROR_TEXT = "Connection timed out to api.example.invalid"
USER_ID = "user-test-1"
ACCOUNT_UUID = "account-test-1"

SENSITIVE_MARKERS = (
    SESSION,
    PROMPT_1,
    PROMPT_2,
    EMAIL,
    WORKSPACE,
    ORG,
    REQUEST_ID,
    MESSAGE_ID,
    CLIENT_REQUEST_ID,
    PROMPT_TEXT,
    RESPONSE_TEXT,
    BASH_COMMAND,
    ERROR_TEXT,
    USER_ID,
    ACCOUNT_UUID,
)

_RESOURCE: dict[str, object] = {
    "service.name": "claude-code",
    "user.email": EMAIL,
    "user.id": USER_ID,
    "user.account_uuid": ACCOUNT_UUID,
    "organization.id": ORG,
    "session.id": SESSION,
    "workspace.host_paths": WORKSPACE,
    "synthetic.tags": ["alpha", "beta"],
    "synthetic.meta": {"note": "kvlist"},
}


def _base_attrs(sequence: int, prompt_id: str) -> dict[str, object]:
    return {
        "session.id": SESSION,
        "prompt.id": prompt_id,
        "event.sequence": sequence,
        "user.email": EMAIL,
        "organization.id": ORG,
        "request_id": REQUEST_ID,
        "client_request_id": CLIENT_REQUEST_ID,
        "message.uuid": MESSAGE_ID,
    }


def _api_request(
    sequence: int,
    prompt_id: str,
    *,
    model: str,
    query_source: str,
    duration_ms: int,
    input_tokens: object,
    output_tokens: int,
    cache_read: int,
    cache_creation: int,
    cost_micros: int,
) -> dict[str, object]:
    return log_record(
        event_name="api_request",
        attributes={
            **_base_attrs(sequence, prompt_id),
            "model": model,
            "query_source": query_source,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_creation_tokens": cache_creation,
            "cost_usd_micros": cost_micros,
            "cost_usd": 99.0,
        },
    )


def build_envelopes() -> list[dict[str, object]]:
    first_logs = [
        log_record(
            event_name="user_prompt",
            attributes={**_base_attrs(1, PROMPT_1), "prompt_length": 42, "prompt": PROMPT_TEXT},
        ),
        _api_request(
            2,
            PROMPT_1,
            model="claude-example",
            query_source="main",
            duration_ms=900,
            input_tokens={"intValue": "400"},
            output_tokens=200,
            cache_read=300,
            cache_creation=50,
            cost_micros=5000,
        ),
        log_record(
            event_name="assistant_response",
            attributes={
                **_base_attrs(3, PROMPT_1),
                "model": "claude-example",
                "query_source": "main",
                "response_length": 80,
                "response": RESPONSE_TEXT,
            },
        ),
        log_record(
            event_name="tool_result",
            attributes={
                **_base_attrs(4, PROMPT_1),
                "tool_name": "Bash",
                "success": "true",
                "duration_ms": 300,
                "tool_input_size_bytes": 200,
                "tool_result_size_bytes": 1000,
                "tool_use_id": "tool-use-1",
                "tool_input": {"command": BASH_COMMAND},
                "tool_parameters": json.dumps({"full_command": BASH_COMMAND}),
            },
        ),
        log_record(event_name="weird_event", attributes=_base_attrs(14, PROMPT_1)),
    ]
    second_logs = [
        log_record(
            event_name="user_prompt",
            attributes={**_base_attrs(5, PROMPT_2), "prompt_length": 20, "prompt": PROMPT_TEXT},
        ),
        _api_request(
            6,
            PROMPT_2,
            model="claude-example",
            query_source="main",
            duration_ms=1000,
            input_tokens=300,
            output_tokens=150,
            cache_read=250,
            cache_creation=25,
            cost_micros=4000,
        ),
        _api_request(
            7,
            PROMPT_2,
            model="claude-example",
            query_source="main",
            duration_ms=600,
            input_tokens=200,
            output_tokens=100,
            cache_read=150,
            cache_creation=15,
            cost_micros=2000,
        ),
        _api_request(
            8,
            PROMPT_2,
            model="claude-other",
            query_source="subagent",
            duration_ms=1500,
            input_tokens=100,
            output_tokens=50,
            cache_read=100,
            cache_creation=10,
            cost_micros=1345,
        ),
        log_record(
            event_name="assistant_response",
            attributes={
                **_base_attrs(9, PROMPT_2),
                "model": "claude-example",
                "query_source": "main",
                "response_length": 10,
                "response": RESPONSE_TEXT,
            },
        ),
        log_record(
            event_name="assistant_response",
            attributes={
                **_base_attrs(10, PROMPT_2),
                "model": "claude-example",
                "query_source": "main",
                "response_length": 10,
                "response": RESPONSE_TEXT,
            },
        ),
        log_record(
            event_name="assistant_response",
            attributes={
                **_base_attrs(11, PROMPT_2),
                "model": "claude-other",
                "query_source": "subagent",
                "response_length": 10,
                "response": RESPONSE_TEXT,
            },
        ),
        log_record(
            event_name="tool_result",
            attributes={
                **_base_attrs(12, PROMPT_2),
                "tool_name": "Bash",
                "success": "false",
                "duration_ms": 700,
                "tool_input_size_bytes": 100,
                "tool_result_size_bytes": 800,
                "error_type": "ShellError",
                "error": ERROR_TEXT,
                "tool_input": {"command": BASH_COMMAND},
                "tool_parameters": json.dumps({"full_command": BASH_COMMAND}),
            },
        ),
        log_record(
            event_name="tool_result",
            attributes={
                **_base_attrs(13, PROMPT_2),
                "tool_name": "Read",
                "success": "true",
                "duration_ms": 200,
                "tool_input_size_bytes": 100,
                "tool_result_size_bytes": 200,
            },
        ),
        log_record(
            event_name="api_error",
            attributes={
                **_base_attrs(15, PROMPT_2),
                "model": "claude-example",
                "status_code": 429,
                "duration_ms": 50,
                "attempt": 2,
                "query_source": "main",
                "error": ERROR_TEXT,
            },
        ),
        _api_request(
            2,
            PROMPT_1,
            model="claude-example",
            query_source="main",
            duration_ms=900,
            input_tokens={"intValue": "400"},
            output_tokens=200,
            cache_read=300,
            cache_creation=50,
            cost_micros=5000,
        ),
    ]
    first_metrics = [
        sum_metric(
            "claude_code.token.usage",
            [
                number_point(
                    value=999,
                    attributes={"type": "input", "model": "claude-example", "query_source": "main"},
                    start_time_unix_nano="10",
                    time_unix_nano="100",
                )
            ],
            temporality=2,
            unit="tokens",
        ),
        sum_metric(
            "claude_code.cost.usage",
            [
                number_point(
                    value=0.099,
                    attributes={"model": "claude-example", "query_source": "main"},
                    start_time_unix_nano="10",
                    time_unix_nano="100",
                )
            ],
            temporality=2,
            unit="USD",
        ),
        sum_metric(
            "claude_code.active_time.total",
            [
                number_point(value=10.0, attributes={"type": "user"}, start_time_unix_nano="1", time_unix_nano="20"),
                number_point(value=20.0, attributes={"type": "cli"}, start_time_unix_nano="1", time_unix_nano="20"),
            ],
            temporality=1,
            unit="s",
        ),
        sum_metric(
            "claude_code.lines_of_code.count",
            [number_point(value=0, attributes={"type": "added", "model": "claude-example"})],
            temporality=1,
        ),
        sum_metric(
            "claude_code.session.count",
            [number_point(value=1, as_string=True, start_time_unix_nano="1", time_unix_nano="20")],
            temporality=2,
        ),
        histogram_metric("claude_code.fake.histogram"),
        sum_metric(
            "custom.unknown.metric",
            [number_point(value=1, attributes={"session.id": SESSION})],
            temporality=1,
        ),
    ]
    second_metrics = [
        sum_metric(
            "claude_code.token.usage",
            [
                number_point(
                    value=1000,
                    attributes={"type": "input", "model": "claude-example", "query_source": "main"},
                    start_time_unix_nano="10",
                    time_unix_nano="200",
                ),
                number_point(
                    value=5,
                    attributes={"type": "input", "model": "claude-example", "query_source": "main"},
                    start_time_unix_nano="99",
                    time_unix_nano="300",
                ),
            ],
            temporality=2,
            unit="tokens",
        ),
        sum_metric(
            "claude_code.active_time.total",
            [
                number_point(value=10.0, attributes={"type": "user"}, start_time_unix_nano="1", time_unix_nano="20"),
                number_point(value=10.0, attributes={"type": "user"}, start_time_unix_nano="1", time_unix_nano="40"),
                number_point(value=20.0, attributes={"type": "cli"}, start_time_unix_nano="1", time_unix_nano="40"),
            ],
            temporality=1,
            unit="s",
        ),
        sum_metric(
            "claude_code.lines_of_code.count",
            [number_point(value=0, attributes={"type": "removed", "model": "claude-example"})],
            temporality=1,
        ),
        sum_metric("claude_code.commit.count", [number_point(value=0)], temporality=1),
        sum_metric("claude_code.pull_request.count", [number_point(value=0)], temporality=1),
        sum_metric(
            "claude_code.code_edit_tool.decision",
            [number_point(value=0, attributes={"tool_name": "Edit", "decision": "accept", "language": "Python"})],
            temporality=1,
        ),
    ]
    return [
        envelope(
            signal="logs",
            payload=resource_logs(first_logs, _RESOURCE),
            received_at="2026-08-15T10:00:00+00:00",
        ),
        envelope(
            signal="logs",
            payload=resource_logs(second_logs, _RESOURCE),
            received_at="2026-08-15T10:01:00+00:00",
        ),
        envelope(
            signal="metrics",
            payload=resource_metrics(first_metrics, _RESOURCE),
            received_at="2026-08-15T10:04:00+00:00",
        ),
        envelope(
            signal="metrics",
            payload=resource_metrics(second_metrics, _RESOURCE),
            received_at="2026-08-15T10:05:00+00:00",
        ),
    ]


def write_synthetic_capture(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in build_envelopes()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "claude_code" / "synthetic-capture.jsonl"
