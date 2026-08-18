"""Allowlist serialization and deterministic text/JSON rendering."""

import json
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime

from coding_agent_performance.trace.report import (
    CompactionPressure,
    DominantTool,
    DurationStats,
    Insights,
    ToolBreakdown,
    TraceSummary,
    UsageSource,
)
from coding_agent_performance.trace.storage import CaptureListing

_USAGE_SOURCE_LABELS: dict[UsageSource, str] = {
    "api_request_events": "API request events",
    "otel_metrics": "OpenTelemetry metrics",
    "none": "none",
}
_TOOL_NAME_MIN_WIDTH = 4
_TOOL_NAME_MAX_WIDTH = 24


def summary_to_dict(summary: TraceSummary) -> dict[str, object]:
    """Serialize a summary through an explicit field allowlist."""
    return {
        "schema_version": summary.schema_version,
        "capture": {
            "source": summary.capture.source,
            "file": summary.capture.file,
            "envelopes": summary.capture.envelopes,
            "log_batches": summary.capture.log_batches,
            "metric_batches": summary.capture.metric_batches,
            "first_received_at": summary.capture.first_received_at,
            "last_received_at": summary.capture.last_received_at,
        },
        "sessions": {
            "count": summary.sessions.count,
            "prompts": summary.sessions.prompts,
            "assistant_responses": summary.sessions.assistant_responses,
            "compactions": summary.sessions.compactions,
            "subagents_completed": summary.sessions.subagents_completed,
        },
        "model_usage": {
            "usage_source": summary.model_usage.usage_source,
            "requests": summary.model_usage.requests,
            "errors": summary.model_usage.errors,
            "refusals": summary.model_usage.refusals,
            "estimated_cost_usd_micros": summary.model_usage.estimated_cost_usd_micros,
            "tokens": {
                "input": summary.model_usage.tokens.input,
                "output": summary.model_usage.tokens.output,
                "cache_read": summary.model_usage.tokens.cache_read,
                "cache_creation": summary.model_usage.tokens.cache_creation,
            },
            "duration_ms": _duration_ms_dict(summary.model_usage.duration_ms),
            "by_model": [
                {
                    "model": row.model,
                    "requests": row.requests,
                    "estimated_cost_usd_micros": row.estimated_cost_usd_micros,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "cache_read_tokens": row.cache_read_tokens,
                    "cache_creation_tokens": row.cache_creation_tokens,
                }
                for row in summary.model_usage.by_model
            ],
            "by_query_source": [
                {
                    "query_source": row.query_source,
                    "requests": row.requests,
                    "estimated_cost_usd_micros": row.estimated_cost_usd_micros,
                }
                for row in summary.model_usage.by_query_source
            ],
        },
        "tools": {
            "calls": summary.tools.calls,
            "successes": summary.tools.successes,
            "failures": summary.tools.failures,
            "success_rate_bps": summary.tools.success_rate_bps,
            "input_bytes": summary.tools.input_bytes,
            "result_bytes": summary.tools.result_bytes,
            "duration_ms": _duration_ms_dict(summary.tools.duration_ms),
            "by_name": [
                {
                    "name": row.name,
                    "calls": row.calls,
                    "successes": row.successes,
                    "failures": row.failures,
                    "success_rate": row.success_rate,
                    "duration_ms_total": row.duration_ms_total,
                    "duration_ms_average": row.duration_ms_average,
                    "input_bytes": row.input_bytes,
                    "result_bytes": row.result_bytes,
                }
                for row in summary.tools.by_name
            ],
        },
        "activity": {
            "active_time_seconds": {
                "user": summary.activity.active_time.user_seconds,
                "cli": summary.activity.active_time.cli_seconds,
            },
            "lines_of_code": {
                "added": summary.activity.lines_of_code.added,
                "removed": summary.activity.lines_of_code.removed,
            },
            "commits": summary.activity.commits,
            "pull_requests": summary.activity.pull_requests,
            "code_edit_decisions": {
                "accepted": summary.activity.code_edit_decisions.accepted,
                "rejected": summary.activity.code_edit_decisions.rejected,
            },
        },
        "coverage": {
            "log_records": summary.coverage.log_records,
            "metric_points": summary.coverage.metric_points,
            "duplicate_log_records": summary.coverage.duplicate_log_records,
            "duplicate_metric_points": summary.coverage.duplicate_metric_points,
            "unsupported_metric_points": summary.coverage.unsupported_metric_points,
            "unknown_otlp_values": summary.coverage.unknown_otlp_values,
            "unknown_events": dict(summary.coverage.unknown_events),
            "unknown_metrics": dict(summary.coverage.unknown_metrics),
            "warnings": list(summary.coverage.warnings),
        },
        "insights": _insights_dict(summary.insights),
    }


def _duration_ms_dict(stats: DurationStats) -> dict[str, int | float | None]:
    return {
        "total": stats.total,
        "average": stats.average,
        "p50": stats.p50,
        "p95": stats.p95,
    }


def _insights_dict(insights: Insights) -> dict[str, object]:
    return {
        "repeated_tool_calls": [
            {
                "tool_name": finding.tool_name,
                "call_count": finding.call_count,
            }
            for finding in insights.repeated_tool_calls
        ],
        "repeated_failed_tool_calls": [
            {
                "tool_name": finding.tool_name,
                "failure_count": finding.failure_count,
            }
            for finding in insights.repeated_failed_tool_calls
        ],
        "high_tool_result_volume": [
            {
                "tool_name": finding.tool_name,
                "result_bytes": finding.result_bytes,
            }
            for finding in insights.high_tool_result_volume
        ],
        "high_tool_failure_rate": [
            {
                "tool_name": finding.tool_name,
                "failed_calls": finding.failed_calls,
                "total_calls": finding.total_calls,
                "failure_rate": {
                    "numerator": finding.failure_rate.numerator,
                    "denominator": finding.failure_rate.denominator,
                },
            }
            for finding in insights.high_tool_failure_rate
        ],
        "dominant_tool": _dominant_tool_dict(insights.dominant_tool),
        "compaction_pressure": _compaction_pressure_dict(insights.compaction_pressure),
    }


def _dominant_tool_dict(finding: DominantTool | None) -> dict[str, str | int] | None:
    if finding is None:
        return None
    return {
        "tool_name": finding.tool_name,
        "call_count": finding.call_count,
        "total_calls": finding.total_calls,
        "share_percent": finding.share_percent,
    }


def _compaction_pressure_dict(finding: CompactionPressure | None) -> dict[str, int] | None:
    if finding is None:
        return None
    return {"compaction_count": finding.compaction_count}


def render_json(summary: TraceSummary) -> str:
    return json.dumps(summary_to_dict(summary), indent=2, allow_nan=False, ensure_ascii=False)


def render_text(summary: TraceSummary) -> str:
    usage = summary.model_usage
    tools = summary.tools
    activity = summary.activity
    coverage = summary.coverage
    insights = summary.insights
    unknown_event_count = sum(count for _name, count in coverage.unknown_events)
    sections = [
        "Capture",
        f"  Source:          {summary.capture.source}",
        f"  File:            {summary.capture.file}",
        f"  Sessions:        {summary.sessions.count}",
        f"  Prompts:         {summary.sessions.prompts}",
        "",
        "Model usage",
        f"  Usage source:    {_USAGE_SOURCE_LABELS[usage.usage_source]}",
        f"  Requests:        {usage.requests}",
        f"  Errors:          {usage.errors}",
        f"  Estimated cost:  {_usd(usage.estimated_cost_usd_micros)}",
        f"  Input tokens:    {_count(usage.tokens.input)}",
        f"  Output tokens:   {_count(usage.tokens.output)}",
        f"  Cache read:      {_count(usage.tokens.cache_read)}",
        f"  Cache creation:  {_count(usage.tokens.cache_creation)}",
        f"  API duration:    {_duration_line(usage.duration_ms)}",
        "",
        "Tools",
        f"  Calls:           {tools.calls}",
        f"  Successes:       {tools.successes}",
        f"  Failures:        {tools.failures}",
        f"  Success rate:    {_bps_percent(tools.success_rate_bps)}",
        f"  Duration:        {_duration_short(tools.duration_ms)}",
    ]
    if tools.by_name:
        sections.extend(["", _tool_table(tools.by_name)])
    insight_lines = _insight_lines(insights)
    if insight_lines:
        sections.extend(["", "Insights", *insight_lines])
    sections.extend(
        [
            "",
            "Activity",
            f"  CLI active time:  {activity.active_time.cli_seconds:.1f}s",
            f"  User active time: {activity.active_time.user_seconds:.1f}s",
            f"  Lines added:      {activity.lines_of_code.added}",
            f"  Lines removed:    {activity.lines_of_code.removed}",
            f"  Commits:          {activity.commits}",
            f"  Pull requests:    {activity.pull_requests}",
            "",
            "Coverage",
            f"  Log records:      {coverage.log_records}",
            f"  Metric points:    {coverage.metric_points}",
            f"  Unknown events:   {unknown_event_count}",
            f"  Unknown OTLP values: {coverage.unknown_otlp_values}",
            f"  Warnings:         {len(coverage.warnings)}",
        ]
    )
    return "\n".join(sections)


def _usd(micros: int) -> str:
    if micros == 0:
        return "$0.000000"
    return f"${micros / 1_000_000:.6f}"


def _count(value: int) -> str:
    return f"{value:,}"


def _percent(successes: int, calls: int) -> str:
    if calls == 0:
        return "n/a"
    return f"{(successes / calls) * 100:.1f}%"


def _bps_percent(bps: int | None) -> str:
    if bps is None:
        return "n/a"
    return f"{bps // 100}.{bps % 100:02d}%"


def _duration_line(stats: DurationStats) -> str:
    if not stats.total and stats.average is None:
        return "n/a"
    parts = [f"{_seconds(stats.total)} total"]
    if stats.average is not None:
        parts.append(f"{_seconds(stats.average)} average")
    if stats.p95 is not None:
        parts.append(f"{_seconds(stats.p95)} p95")
    return ", ".join(parts)


def _duration_short(stats: DurationStats) -> str:
    if not stats.total and stats.average is None:
        return "n/a"
    return f"{_seconds(stats.total)} total"


def _seconds(value: int | float) -> str:
    return f"{value / 1000:.2f}s"


def _insight_lines(insights: Insights) -> list[str]:
    lines: list[str] = []
    _append_insight_group(
        lines,
        "Repeated tool calls",
        tuple(f"- {finding.tool_name}: {finding.call_count} calls" for finding in insights.repeated_tool_calls),
    )
    _append_insight_group(
        lines,
        "Repeated failed tool calls",
        tuple(
            f"- {finding.tool_name}: {finding.failure_count} failures"
            for finding in insights.repeated_failed_tool_calls
        ),
    )
    _append_insight_group(
        lines,
        "High tool result volume",
        tuple(
            f"- {finding.tool_name}: {finding.result_bytes} result bytes"
            for finding in insights.high_tool_result_volume
        ),
    )
    _append_insight_group(
        lines,
        "High tool failure rate",
        tuple(
            (
                f"- {finding.tool_name}: {finding.failed_calls} failed of "
                f"{finding.total_calls} calls "
                f"({finding.failure_rate.numerator}/{finding.failure_rate.denominator})"
            )
            for finding in insights.high_tool_failure_rate
        ),
    )
    if insights.dominant_tool is not None:
        finding = insights.dominant_tool
        _append_insight_group(
            lines,
            "Dominant tool",
            (f"- {finding.tool_name}: {finding.call_count}/{finding.total_calls} calls ({finding.share_percent}%)",),
        )
    if insights.compaction_pressure is not None:
        finding = insights.compaction_pressure
        _append_insight_group(
            lines,
            "Compaction pressure",
            (f"- {finding.compaction_count} compactions",),
        )
    return lines


def _append_insight_group(lines: list[str], heading: str, entries: tuple[str, ...]) -> None:
    if not entries:
        return
    lines.append(heading)
    lines.extend(entries)


def _tool_table(rows: tuple[ToolBreakdown, ...]) -> str:
    width = _tool_name_width(rows)
    lines = [f"  {'Tool':<{width}}  Calls  Success  Failures  Avg"]
    for row in rows:
        rate = _percent(row.successes, row.calls)
        average = "n/a" if row.duration_ms_average is None else f"{row.duration_ms_average:.0f}ms"
        lines.append(f"  {_truncate(row.name, width):<{width}}{row.calls:>7}{rate:>9}{row.failures:>10}  {average}")
    return "\n".join(lines)


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return f"{value[: width - 3]}..."


def _tool_name_width(rows: tuple[ToolBreakdown, ...]) -> int:
    widest = max((len(row.name) for row in rows), default=_TOOL_NAME_MIN_WIDTH)
    return min(_TOOL_NAME_MAX_WIDTH, max(_TOOL_NAME_MIN_WIDTH, widest))


def render_capture_list(captures: Sequence[CaptureListing]) -> str:
    if not captures:
        return "No capture files found."
    return "\n".join(render_capture_listing(item) for item in captures)


def render_capture_listing(listing: CaptureListing) -> str:
    return f"{escape_filename(listing.name)}  {listing.size_bytes}  {format_utc_timestamp(listing.modified_at)}"


def format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def escape_filename(name: str) -> str:
    pieces: list[str] = []
    for char in name:
        match char:
            case "\\":
                pieces.append("\\\\")
            case "\n":
                pieces.append("\\n")
            case "\r":
                pieces.append("\\r")
            case "\t":
                pieces.append("\\t")
            case _:
                category = unicodedata.category(char)
                if category.startswith("C") or category in {"Zl", "Zp"}:
                    code = ord(char)
                    if code <= 0xFF:
                        pieces.append(f"\\x{code:02x}")
                    elif code <= 0xFFFF:
                        pieces.append(f"\\u{code:04x}")
                    else:
                        pieces.append(f"\\U{code:08x}")
                else:
                    pieces.append(char)
    return "".join(pieces)
