"""Summarize a CAPT capture into a trace report."""

from pathlib import Path

from coding_agent_performance.adapters.claude_code.normalizer import normalize_decoded
from coding_agent_performance.trace.aggregation import IncrementalSummarizer
from coding_agent_performance.trace.capture import CaptureReader
from coding_agent_performance.trace.otel import decode_otlp
from coding_agent_performance.trace.report import TraceSummary

__all__ = ["TraceSummary", "summarize_capture"]


def summarize_capture(path: Path) -> TraceSummary:
    reader = CaptureReader(path)
    summarizer = IncrementalSummarizer(filename=path.name)
    for envelope in reader:
        decoded = decode_otlp(envelope.signal, envelope.payload)
        records = normalize_decoded(decoded)
        summarizer.add(
            envelope,
            records,
            log_count=len(decoded.logs),
            metric_count=len(decoded.metrics),
            unsupported=decoded.unsupported_metric_points,
            unknown_otlp_values=decoded.unknown_value_count,
        )
    return summarizer.finish(path)
