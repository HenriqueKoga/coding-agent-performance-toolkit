"""Provider-neutral records used by the incremental summarizer."""

from dataclasses import dataclass
from typing import Literal

type MetricKind = Literal["sum", "gauge"]
type AggregationTemporality = Literal["delta", "cumulative"]
type MetricAttributes = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ModelRequest:
    session_id: str | None
    prompt_id: str | None
    model: str
    query_source: str | None
    duration_ms: int | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    estimated_cost_usd_micros: int
    event_sequence: int | None


@dataclass(frozen=True, slots=True)
class ModelRequestError:
    session_id: str | None
    prompt_id: str | None
    model: str | None
    status_code: int | None
    duration_ms: int | None
    attempt_count: int | None
    query_source: str | None
    event_sequence: int | None


@dataclass(frozen=True, slots=True)
class ToolExecution:
    session_id: str | None
    prompt_id: str | None
    tool_name: str
    success: bool
    duration_ms: int | None
    input_size_bytes: int | None
    result_size_bytes: int | None
    error_type: str | None
    tool_use_id: str | None
    event_sequence: int | None


@dataclass(frozen=True, slots=True)
class UserPrompt:
    session_id: str | None
    prompt_id: str | None
    prompt_length: int | None
    event_sequence: int | None


@dataclass(frozen=True, slots=True)
class AssistantResponse:
    session_id: str | None
    prompt_id: str | None
    model: str | None
    query_source: str | None
    response_length: int | None
    event_sequence: int | None


@dataclass(frozen=True, slots=True)
class ActivityMeasurement:
    name: str
    value: int | float
    unit: str
    attributes: MetricAttributes
    start_time_unix_nano: int | None
    time_unix_nano: int | None
    aggregation_temporality: AggregationTemporality | None
    kind: MetricKind


@dataclass(frozen=True, slots=True)
class NamedLifecycleEvent:
    name: str
    session_id: str | None
    event_sequence: int | None


@dataclass(frozen=True, slots=True)
class UnknownEvent:
    name: str
    session_id: str | None
    event_sequence: int | None


@dataclass(frozen=True, slots=True)
class UnknownMetric:
    name: str


type DomainRecord = (
    ModelRequest
    | ModelRequestError
    | ToolExecution
    | UserPrompt
    | AssistantResponse
    | ActivityMeasurement
    | NamedLifecycleEvent
    | UnknownEvent
    | UnknownMetric
)
