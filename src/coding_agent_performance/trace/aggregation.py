"""Orchestrate incremental aggregation of domain records into a trace summary."""

from pathlib import Path
from typing import Final

from coding_agent_performance.trace.accumulators import (
    CaptureAccumulator,
    CoverageAccumulator,
    MetricAccumulator,
    SessionAccumulator,
    ToolAccumulator,
    UsageAccumulator,
)
from coding_agent_performance.trace.capture import CaptureEnvelope, CaptureError
from coding_agent_performance.trace.insights import InsightAnalyzer
from coding_agent_performance.trace.records import (
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
from coding_agent_performance.trace.report import TraceSummary

SUMMARY_SCHEMA_VERSION: Final = 1


class IncrementalSummarizer:
    """Coordinate capture ingestion and finalize an immutable summary."""

    def __init__(self, filename: str) -> None:
        self._capture = CaptureAccumulator(filename=filename)
        self._sessions = SessionAccumulator()
        self._usage = UsageAccumulator()
        self._tools = ToolAccumulator()
        self._metrics = MetricAccumulator()
        self._coverage = CoverageAccumulator()

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
        self._capture.add(envelope)
        self._coverage.add_counts(
            log_count=log_count,
            metric_count=metric_count,
            unsupported=unsupported,
            unknown_otlp_values=unknown_otlp_values,
        )
        for record in records:
            self._ingest(record)

    def finish(self, path: Path) -> TraceSummary:
        if not self._coverage.has_recognized_telemetry():
            raise CaptureError(path, "no recognized telemetry")
        tools = self._tools.snapshot()
        return TraceSummary(
            schema_version=SUMMARY_SCHEMA_VERSION,
            capture=self._capture.snapshot(),
            sessions=self._sessions.snapshot(
                metric_session_count=int(self._metrics.total("claude_code.session.count"))
            ),
            model_usage=self._usage.snapshot(self._metrics),
            tools=tools,
            activity=self._metrics.activity_stats(),
            coverage=self._coverage.snapshot(),
            insights=InsightAnalyzer(tools=tools).analyze(),
        )

    def _ingest(self, record: DomainRecord) -> None:
        if isinstance(record, ActivityMeasurement):
            result = self._metrics.add(record)
            if result.duplicate:
                self._coverage.record_duplicate_point()
                return
            if result.unknown_temporality:
                self._coverage.warn_temporality()
            return
        if isinstance(record, UnknownMetric):
            self._coverage.record_unknown_metric(record.name)
            return
        identity = _log_identity(record)
        if identity is not None:
            if not self._coverage.observe_log(identity):
                return
        session_id = getattr(record, "session_id", None)
        if isinstance(session_id, str) and session_id:
            self._sessions.add_id(session_id)
        if isinstance(record, ModelRequest):
            self._usage.add_request(record)
        elif isinstance(record, ModelRequestError):
            self._usage.add_error()
        elif isinstance(record, ToolExecution):
            self._tools.add(record)
        elif isinstance(record, UserPrompt):
            self._sessions.add_prompt()
        elif isinstance(record, AssistantResponse):
            self._sessions.add_assistant_response()
        elif isinstance(record, NamedLifecycleEvent):
            if record.name == "api_refusal":
                self._usage.add_refusal()
            elif record.name == "compaction":
                self._sessions.add_compaction()
            elif record.name == "subagent_completed":
                self._sessions.add_subagent_completed()
        elif isinstance(record, UnknownEvent):
            self._coverage.record_unknown_event(record.name)


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
