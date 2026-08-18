"""Pure comparison of two immutable trace summaries."""

from dataclasses import dataclass
from typing import Final

from coding_agent_performance.trace.report import TraceSummary

COMPARISON_SCHEMA_VERSION: Final = 1
COMPARISON_METRIC_KEYS: Final = (
    "tool_calls",
    "tool_failures",
    "tool_result_bytes",
    "model_requests",
    "estimated_cost_usd_micros",
    "input_tokens",
    "output_tokens",
    "session_compactions",
)


@dataclass(frozen=True, slots=True)
class MetricComparison:
    available: bool
    baseline: int | None
    candidate: int | None
    delta: int | None

    def __post_init__(self) -> None:
        if self.available:
            if self.baseline is None or self.candidate is None or self.delta is None:
                raise ValueError("available metric comparison requires integer values")
            if self.delta != self.candidate - self.baseline:
                raise ValueError("delta must equal candidate minus baseline")
            return
        if self.baseline is not None or self.candidate is not None or self.delta is not None:
            raise ValueError("unavailable metric comparison must omit numeric values")


@dataclass(frozen=True, slots=True)
class TraceComparison:
    tool_calls: MetricComparison
    tool_failures: MetricComparison
    tool_result_bytes: MetricComparison
    model_requests: MetricComparison
    estimated_cost_usd_micros: MetricComparison
    input_tokens: MetricComparison
    output_tokens: MetricComparison
    session_compactions: MetricComparison


def compare_summaries(baseline: TraceSummary, candidate: TraceSummary) -> TraceComparison:
    return TraceComparison(
        tool_calls=_compare_slot(
            baseline.comparison_availability.tool_calls,
            candidate.comparison_availability.tool_calls,
            baseline.tools.calls,
            candidate.tools.calls,
        ),
        tool_failures=_compare_slot(
            baseline.comparison_availability.tool_failures,
            candidate.comparison_availability.tool_failures,
            baseline.tools.failures,
            candidate.tools.failures,
        ),
        tool_result_bytes=_compare_slot(
            baseline.comparison_availability.tool_result_bytes,
            candidate.comparison_availability.tool_result_bytes,
            baseline.tools.result_bytes,
            candidate.tools.result_bytes,
        ),
        model_requests=_compare_slot(
            baseline.comparison_availability.model_requests,
            candidate.comparison_availability.model_requests,
            baseline.model_usage.requests,
            candidate.model_usage.requests,
        ),
        estimated_cost_usd_micros=_compare_slot(
            baseline.comparison_availability.estimated_cost_usd_micros,
            candidate.comparison_availability.estimated_cost_usd_micros,
            baseline.model_usage.estimated_cost_usd_micros,
            candidate.model_usage.estimated_cost_usd_micros,
        ),
        input_tokens=_compare_slot(
            baseline.comparison_availability.input_tokens,
            candidate.comparison_availability.input_tokens,
            baseline.model_usage.tokens.input,
            candidate.model_usage.tokens.input,
        ),
        output_tokens=_compare_slot(
            baseline.comparison_availability.output_tokens,
            candidate.comparison_availability.output_tokens,
            baseline.model_usage.tokens.output,
            candidate.model_usage.tokens.output,
        ),
        session_compactions=_compare_slot(
            baseline.comparison_availability.session_compactions,
            candidate.comparison_availability.session_compactions,
            baseline.sessions.compactions,
            candidate.sessions.compactions,
        ),
    )


def _compare_slot(
    baseline_available: bool,
    candidate_available: bool,
    baseline_value: int,
    candidate_value: int,
) -> MetricComparison:
    if not baseline_available or not candidate_available:
        return MetricComparison(available=False, baseline=None, candidate=None, delta=None)
    return MetricComparison(
        available=True,
        baseline=baseline_value,
        candidate=candidate_value,
        delta=candidate_value - baseline_value,
    )
