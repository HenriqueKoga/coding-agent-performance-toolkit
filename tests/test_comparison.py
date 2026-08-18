import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_agent_performance.cli import app
from coding_agent_performance.trace.comparison import (
    COMPARISON_METRIC_KEYS,
    COMPARISON_SCHEMA_VERSION,
    MetricComparison,
    compare_summaries,
)
from coding_agent_performance.trace.rendering import (
    comparison_to_dict,
    render_comparison_json,
    render_comparison_text,
    summary_to_dict,
)
from coding_agent_performance.trace.report import ComparisonAvailability, TraceSummary
from coding_agent_performance.trace.summary import summarize_capture
from tests.helpers.otlp import envelope, log_record, number_point, resource_logs, resource_metrics, sum_metric
from tests.helpers.synthetic_capture import FIXTURE_PATH, SENSITIVE_MARKERS, write_synthetic_capture

runner = CliRunner()
_METRIC_SLOT_KEYS = ("available", "baseline", "candidate", "delta")


def _write_capture(path: Path, *rows: dict[str, object]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _logs(*records: dict[str, object]) -> dict[str, object]:
    return envelope(signal="logs", payload=resource_logs(list(records)))


def _metrics(*metrics: dict[str, object]) -> dict[str, object]:
    return envelope(signal="metrics", payload=resource_metrics(list(metrics)))


def _tool(
    *,
    name: str = "Read",
    success: object = True,
    result_bytes: object = 10,
    include_success: bool = True,
    include_result: bool = True,
) -> dict[str, object]:
    attributes: dict[str, object] = {"tool_name": name}
    if include_success:
        attributes["success"] = success
    if include_result:
        attributes["tool_result_size_bytes"] = result_bytes
    return log_record(event_name="tool_result", attributes=attributes)


def _api(
    *,
    input_tokens: object = 10,
    output_tokens: object = 4,
    cost_micros: object = 12,
    include_input: bool = True,
    include_output: bool = True,
    include_cost: bool = True,
    cost_usd: object | None = None,
) -> dict[str, object]:
    attributes: dict[str, object] = {"model": "claude-example"}
    if include_input:
        attributes["input_tokens"] = input_tokens
    if include_output:
        attributes["output_tokens"] = output_tokens
    if include_cost and cost_usd is None:
        attributes["cost_usd_micros"] = cost_micros
    if include_cost and cost_usd is not None:
        attributes["cost_usd"] = cost_usd
    return log_record(event_name="api_request", attributes=attributes)


def _prompt() -> dict[str, object]:
    return log_record(event_name="user_prompt", attributes={"prompt_length": 1})


def _compaction() -> dict[str, object]:
    return log_record(event_name="compaction", attributes={"session.id": "session-test-1"})


def _token_metric(token_type: str, value: int) -> dict[str, object]:
    return sum_metric(
        "claude_code.token.usage",
        [number_point(value=value, attributes={"type": token_type, "model": "claude-example"})],
        temporality=1,
    )


def _cost_metric(value: float) -> dict[str, object]:
    return sum_metric(
        "claude_code.cost.usage",
        [number_point(value=value, attributes={"model": "claude-example"})],
        temporality=1,
    )


def _activity_metric() -> dict[str, object]:
    return sum_metric("claude_code.commit.count", [number_point(value=2)], temporality=1)


def test_model_requests_require_an_api_request_event(tmp_path: Path) -> None:
    with_request = summarize_capture(_write_capture(tmp_path / "requests.jsonl", _logs(_api())))
    metrics_only = summarize_capture(
        _write_capture(tmp_path / "metrics.jsonl", _metrics(_token_metric("input", 10), _cost_metric(0.000012)))
    )
    none = summarize_capture(_write_capture(tmp_path / "none.jsonl", _logs(_prompt())))
    assert with_request.comparison_availability.model_requests is True
    assert with_request.model_usage.requests == 1
    assert metrics_only.comparison_availability.model_requests is False
    assert metrics_only.model_usage.requests == 0
    assert none.comparison_availability.model_requests is False


def test_cost_and_token_availability_are_independent_for_api_events(tmp_path: Path) -> None:
    partial = summarize_capture(
        _write_capture(tmp_path / "partial-api.jsonl", _logs(_api(include_output=False, include_cost=False)))
    )
    availability = partial.comparison_availability
    assert availability.model_requests is True
    assert availability.input_tokens is True
    assert availability.output_tokens is False
    assert availability.estimated_cost_usd_micros is False
    assert partial.model_usage.tokens.input == 10
    assert partial.model_usage.tokens.output == 0
    assert partial.model_usage.estimated_cost_usd_micros == 0


def test_incomplete_api_cost_does_not_use_metric_fallback(tmp_path: Path) -> None:
    summary = summarize_capture(
        _write_capture(
            tmp_path / "mixed.jsonl",
            _logs(_api(include_cost=False)),
            _metrics(_cost_metric(0.099)),
        )
    )
    assert summary.model_usage.usage_source == "api_request_events"
    assert summary.comparison_availability.estimated_cost_usd_micros is False
    assert summary.model_usage.estimated_cost_usd_micros == 0


def test_otel_cost_and_tokens_are_independently_available(tmp_path: Path) -> None:
    partial = summarize_capture(
        _write_capture(tmp_path / "partial-metrics.jsonl", _metrics(_token_metric("input", 0), _activity_metric()))
    )
    complete = summarize_capture(
        _write_capture(
            tmp_path / "complete-metrics.jsonl",
            _metrics(_token_metric("input", 3), _token_metric("output", 0), _cost_metric(0.0)),
        )
    )
    assert partial.comparison_availability.input_tokens is True
    assert partial.comparison_availability.output_tokens is False
    assert partial.comparison_availability.estimated_cost_usd_micros is False
    assert partial.model_usage.tokens.input == 0
    assert complete.comparison_availability.input_tokens is True
    assert complete.comparison_availability.output_tokens is True
    assert complete.comparison_availability.estimated_cost_usd_micros is True
    assert complete.model_usage.tokens.output == 0
    assert complete.model_usage.estimated_cost_usd_micros == 0


def test_tool_calls_need_tool_events_and_failures_need_valid_success(tmp_path: Path) -> None:
    metrics_only = summarize_capture(_write_capture(tmp_path / "metrics.jsonl", _metrics(_activity_metric())))
    log_backed = summarize_capture(_write_capture(tmp_path / "logs.jsonl", _logs(_prompt())))
    valid = summarize_capture(_write_capture(tmp_path / "valid.jsonl", _logs(_tool(success=False, result_bytes=0))))
    missing = summarize_capture(_write_capture(tmp_path / "missing.jsonl", _logs(_tool(include_success=False))))
    invalid = summarize_capture(_write_capture(tmp_path / "invalid.jsonl", _logs(_tool(success="maybe"))))
    assert metrics_only.comparison_availability.tool_calls is False
    assert metrics_only.comparison_availability.tool_failures is False
    assert log_backed.comparison_availability.tool_calls is False
    assert valid.comparison_availability.tool_calls is True
    assert valid.comparison_availability.tool_failures is True
    assert valid.tools.failures == 1
    assert missing.comparison_availability.tool_calls is True
    assert missing.comparison_availability.tool_failures is False
    assert missing.tools.failures == 0
    assert invalid.comparison_availability.tool_calls is True
    assert invalid.comparison_availability.tool_failures is False


def test_tool_result_bytes_require_complete_size_evidence(tmp_path: Path) -> None:
    complete = summarize_capture(_write_capture(tmp_path / "complete.jsonl", _logs(_tool(result_bytes=0))))
    missing = summarize_capture(_write_capture(tmp_path / "missing.jsonl", _logs(_tool(include_result=False))))
    mixed = summarize_capture(
        _write_capture(tmp_path / "mixed.jsonl", _logs(_tool(result_bytes=8), _tool(name="Bash", include_result=False)))
    )
    assert complete.comparison_availability.tool_result_bytes is True
    assert complete.tools.result_bytes == 0
    assert missing.comparison_availability.tool_result_bytes is False
    assert mixed.comparison_availability.tool_result_bytes is False


def test_compaction_availability_uses_log_coverage(tmp_path: Path) -> None:
    logs = summarize_capture(_write_capture(tmp_path / "logs.jsonl", _logs(_prompt())))
    with_event = summarize_capture(_write_capture(tmp_path / "compaction.jsonl", _logs(_prompt(), _compaction())))
    metrics_only = summarize_capture(_write_capture(tmp_path / "metrics.jsonl", _metrics(_activity_metric())))
    assert logs.comparison_availability.session_compactions is True
    assert logs.sessions.compactions == 0
    assert with_event.comparison_availability.session_compactions is True
    assert with_event.sessions.compactions == 1
    assert metrics_only.comparison_availability.session_compactions is False


def test_observed_zero_is_available_except_for_model_requests(tmp_path: Path) -> None:
    observed_zero = summarize_capture(
        _write_capture(
            tmp_path / "zero.jsonl",
            _logs(_prompt(), _tool(success=True, result_bytes=0), _api(input_tokens=0, output_tokens=0, cost_micros=0)),
        )
    )
    no_usage = summarize_capture(_write_capture(tmp_path / "no-usage.jsonl", _logs(_prompt())))
    availability = observed_zero.comparison_availability
    assert availability.tool_calls is True
    assert availability.tool_failures is True
    assert availability.tool_result_bytes is True
    assert availability.model_requests is True
    assert availability.estimated_cost_usd_micros is True
    assert availability.input_tokens is True
    assert availability.output_tokens is True
    assert availability.session_compactions is True
    assert observed_zero.tools.failures == 0
    assert observed_zero.tools.result_bytes == 0
    assert observed_zero.model_usage.estimated_cost_usd_micros == 0
    assert observed_zero.model_usage.tokens.input == 0
    assert observed_zero.sessions.compactions == 0
    assert no_usage.comparison_availability.model_requests is False
    assert no_usage.model_usage.requests == 0


def test_metric_comparison_contract() -> None:
    available = MetricComparison(available=True, baseline=10, candidate=8, delta=-2)
    unavailable = MetricComparison(available=False, baseline=None, candidate=None, delta=None)
    assert available.delta == available.candidate - available.baseline
    assert unavailable.available is False
    with pytest.raises(ValueError):
        MetricComparison(available=True, baseline=1, candidate=2, delta=0)
    with pytest.raises(ValueError):
        MetricComparison(available=True, baseline=None, candidate=2, delta=2)
    with pytest.raises(ValueError):
        MetricComparison(available=False, baseline=0, candidate=0, delta=0)


def test_compare_summaries_reports_signed_deltas(tmp_path: Path) -> None:
    baseline = summarize_capture(
        _write_capture(
            tmp_path / "baseline.jsonl",
            _logs(
                _prompt(),
                _tool(success=True, result_bytes=20),
                _tool(name="Bash", success=False, result_bytes=5),
                _api(input_tokens=20, output_tokens=8, cost_micros=100),
                _compaction(),
            ),
        )
    )
    candidate = summarize_capture(
        _write_capture(
            tmp_path / "candidate.jsonl",
            _logs(
                _prompt(),
                _tool(success=True, result_bytes=10),
                _api(input_tokens=10, output_tokens=9, cost_micros=40),
            ),
        )
    )
    comparison = compare_summaries(baseline, candidate)
    assert comparison.tool_calls.delta == -1
    assert comparison.tool_failures.delta == -1
    assert comparison.tool_result_bytes.delta == -15
    assert comparison.model_requests.delta == 0
    assert comparison.estimated_cost_usd_micros.delta == -60
    assert comparison.input_tokens.delta == -10
    assert comparison.output_tokens.delta == 1
    assert comparison.session_compactions.delta == -1


def test_compare_summaries_keeps_unavailable_slots_null(tmp_path: Path) -> None:
    baseline = summarize_capture(_write_capture(tmp_path / "baseline.jsonl", _logs(_prompt())))
    candidate = summarize_capture(_write_capture(tmp_path / "candidate.jsonl", _metrics(_activity_metric())))
    comparison = compare_summaries(baseline, candidate)
    assert comparison.model_requests.available is False
    assert comparison.model_requests.baseline is None
    assert comparison.model_requests.candidate is None
    assert comparison.model_requests.delta is None
    assert comparison.session_compactions.available is False
    assert comparison.tool_calls.available is False


def test_compare_help(visible: Callable[[str], str]) -> None:
    result = runner.invoke(app, ["trace", "compare", "--help"], color=False)
    text = visible(result.output)
    assert result.exit_code == 0
    assert "baseline" in text.lower()
    assert "candidate" in text.lower()
    assert "--format" in text
    assert "json" in text
    assert "text" in text


def test_cli_identical_increased_decreased_and_unavailable(tmp_path: Path) -> None:
    identical = _write_capture(tmp_path / "identical.jsonl", _logs(_tool(), _api()))
    increased = _write_capture(
        tmp_path / "increased.jsonl",
        _logs(_tool(), _tool(name="Bash"), _api(input_tokens=30, output_tokens=8, cost_micros=40)),
    )
    zero_requests = _write_capture(tmp_path / "zero-requests.jsonl", _logs(_prompt(), _tool()))
    result = runner.invoke(app, ["trace", "compare", str(identical), str(identical)], color=False)
    assert result.exit_code == 0
    assert "tool_calls: 1 → 1 (delta 0)" in result.stdout
    increased_result = runner.invoke(app, ["trace", "compare", str(identical), str(increased)], color=False)
    assert "tool_calls: 1 → 2 (delta 1)" in increased_result.stdout
    decreased_result = runner.invoke(app, ["trace", "compare", str(increased), str(identical)], color=False)
    assert "tool_calls: 2 → 1 (delta -1)" in decreased_result.stdout
    unavailable = runner.invoke(app, ["trace", "compare", str(identical), str(zero_requests)], color=False)
    assert "model_requests: unavailable" in unavailable.stdout
    assert "NaN" not in unavailable.stdout
    assert "Infinity" not in unavailable.stdout


def test_cli_observed_zero_and_mixed_availability(tmp_path: Path) -> None:
    observed_zero = _write_capture(
        tmp_path / "zero.jsonl",
        _logs(_prompt(), _tool(success=True, result_bytes=0), _api(input_tokens=0, output_tokens=0, cost_micros=0)),
    )
    metrics_only = _write_capture(tmp_path / "metrics.jsonl", _metrics(_activity_metric()))
    result = runner.invoke(app, ["trace", "compare", str(observed_zero), str(observed_zero)], color=False)
    assert result.exit_code == 0
    assert "tool_failures: 0 → 0 (delta 0)" in result.stdout
    assert "tool_result_bytes: 0 → 0 (delta 0)" in result.stdout
    assert "estimated_cost_usd_micros: 0 → 0 (delta 0)" in result.stdout
    mixed = runner.invoke(app, ["trace", "compare", str(observed_zero), str(metrics_only)], color=False)
    assert "tool_calls: unavailable" in mixed.stdout
    assert "session_compactions: unavailable" in mixed.stdout
    assert "model_requests: unavailable" in mixed.stdout


def test_same_file_reuses_one_summary_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write_capture(tmp_path / "same.jsonl", _logs(_tool(), _api()))
    calls: list[Path] = []
    original = summarize_capture

    def tracked(capture: Path) -> TraceSummary:
        summary = original(capture)
        calls.append(capture)
        with capture.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_logs(_tool(name="Bash"))) + "\n")
        return summary

    monkeypatch.setattr("coding_agent_performance.trace.cli.summarize_capture", tracked)
    result = runner.invoke(app, ["trace", "compare", str(path), str(path), "--format", "json"], color=False)
    parsed = json.loads(result.stdout)
    assert result.exit_code == 0
    assert calls == [path]
    assert parsed["metrics"]["tool_calls"] == {"available": True, "baseline": 1, "candidate": 1, "delta": 0}


def test_same_file_symlink_reuses_one_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write_capture(tmp_path / "capture.jsonl", _logs(_tool(), _api()))
    alias = tmp_path / "alias.jsonl"
    alias.symlink_to(path)
    calls: list[Path] = []
    original = summarize_capture

    def tracked(capture: Path) -> TraceSummary:
        calls.append(capture)
        return original(capture)

    monkeypatch.setattr("coding_agent_performance.trace.cli.summarize_capture", tracked)
    result = runner.invoke(app, ["trace", "compare", str(path), str(alias)], color=False)
    assert result.exit_code == 0
    assert len(calls) == 1
    assert "delta 0" in result.stdout


def test_compare_errors_are_payload_free(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    invalid = tmp_path / "bad.jsonl"
    invalid.write_text("{not-json\nsecret-payload\n", encoding="utf-8")
    missing_result = runner.invoke(app, ["trace", "compare", str(missing), str(invalid)], color=False)
    assert missing_result.exit_code == 1
    assert "does not exist" in missing_result.output
    assert "Traceback" not in missing_result.output
    assert str(missing) not in missing_result.output
    invalid_result = runner.invoke(app, ["trace", "compare", str(invalid), str(invalid)], color=False)
    assert invalid_result.exit_code == 1
    assert "invalid JSON" in invalid_result.output
    assert "bad.jsonl:1" in invalid_result.output
    assert "{not-json" not in invalid_result.output
    assert "secret-payload" not in invalid_result.output
    assert "Traceback" not in invalid_result.output
    assert str(invalid.resolve()) not in invalid_result.output


def test_compare_oserror_uses_basename(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "capture.jsonl"
    path.write_text("{}\n", encoding="utf-8")

    def boom(_path: Path) -> TraceSummary:
        raise OSError("permission denied")

    monkeypatch.setattr("coding_agent_performance.trace.cli.summarize_capture", boom)
    result = runner.invoke(app, ["trace", "compare", str(path), str(path)], color=False)
    assert result.exit_code == 1
    assert "permission denied" in result.output
    assert "capture.jsonl" in result.output
    assert str(path.resolve()) not in result.output
    assert "Traceback" not in result.output


def test_json_v1_contract_and_key_order(tmp_path: Path) -> None:
    baseline = _write_capture(tmp_path / "baseline.jsonl", _logs(_prompt(), _tool(), _api(), _compaction()))
    candidate = _write_capture(tmp_path / "candidate.jsonl", _logs(_prompt(), _api()))
    result = runner.invoke(app, ["trace", "compare", str(baseline), str(candidate), "--format", "json"], color=False)
    parsed = json.loads(result.stdout)
    assert result.exit_code == 0
    assert not result.stderr
    assert list(parsed) == ["schema_version", "metrics"]
    assert parsed["schema_version"] == COMPARISON_SCHEMA_VERSION
    assert list(parsed["metrics"]) == list(COMPARISON_METRIC_KEYS)
    for key in COMPARISON_METRIC_KEYS:
        assert list(parsed["metrics"][key]) == list(_METRIC_SLOT_KEYS)
    available = parsed["metrics"]["model_requests"]
    assert available["available"] is True
    assert isinstance(available["baseline"], int)
    assert isinstance(available["candidate"], int)
    assert isinstance(available["delta"], int)
    unavailable = parsed["metrics"]["tool_calls"]
    assert unavailable == {"available": False, "baseline": None, "candidate": None, "delta": None}
    raw = result.stdout
    assert raw.index('"schema_version"') < raw.index('"metrics"')
    assert raw.index('"tool_calls"') < raw.index('"session_compactions"')
    assert "NaN" not in raw


def test_json_serialization_is_deterministic(tmp_path: Path) -> None:
    baseline = write_synthetic_capture(tmp_path / "baseline.jsonl")
    candidate = write_synthetic_capture(tmp_path / "candidate.jsonl")
    first = runner.invoke(app, ["trace", "compare", str(baseline), str(candidate), "--format", "json"], color=False)
    second = runner.invoke(app, ["trace", "compare", str(baseline), str(candidate), "--format", "json"], color=False)
    assert first.stdout == second.stdout
    parsed = json.loads(first.stdout)
    rendered = comparison_to_dict(compare_summaries(summarize_capture(baseline), summarize_capture(candidate)))
    assert parsed == rendered
    assert set(parsed) == {"schema_version", "metrics"}
    assert set(parsed["metrics"]) == set(COMPARISON_METRIC_KEYS)


def test_text_and_json_agree_and_omit_sensitive_data(tmp_path: Path) -> None:
    baseline = write_synthetic_capture(tmp_path / "baseline.jsonl")
    candidate = write_synthetic_capture(tmp_path / "candidate.jsonl")
    text = runner.invoke(app, ["trace", "compare", str(baseline), str(candidate)], color=False)
    json_result = runner.invoke(
        app, ["trace", "compare", str(baseline), str(candidate), "--format", "json"], color=False
    )
    parsed = json.loads(json_result.stdout)
    metrics = parsed["metrics"]
    assert text.exit_code == 0
    assert json_result.exit_code == 0
    assert isinstance(metrics, dict)
    for key, slot in metrics.items():
        assert isinstance(key, str)
        assert isinstance(slot, dict)
        if slot["available"]:
            line = f"{key}: {slot['baseline']} → {slot['candidate']} (delta {slot['delta']})"
            assert line in text.stdout
        else:
            assert f"{key}: unavailable" in text.stdout
    for output in (text.stdout, json_result.stdout):
        assert str(baseline.resolve()) not in output
        assert str(candidate.resolve()) not in output
        assert "claude_code." not in output
        for marker in SENSITIVE_MARKERS:
            assert marker not in output


def test_fixture_summary_contract_is_unchanged() -> None:
    payload = summary_to_dict(summarize_capture(FIXTURE_PATH))
    availability = summarize_capture(FIXTURE_PATH).comparison_availability
    assert isinstance(availability, ComparisonAvailability)
    assert "comparison_availability" not in payload
    assert payload["schema_version"] == 1
    assert payload["tools"]["calls"] == 3
    assert payload["model_usage"]["requests"] == 4
    assert payload["sessions"]["compactions"] == 0
    comparison = compare_summaries(summarize_capture(FIXTURE_PATH), summarize_capture(FIXTURE_PATH))
    assert "synthetic-capture.jsonl" not in render_comparison_json(comparison)
    assert render_comparison_text(comparison).startswith("Comparison")
