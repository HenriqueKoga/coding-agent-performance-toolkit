"""Deterministic text and JSON renderers for trace summaries."""

import json

from coding_agent_performance.trace.summary import DurationStats, ToolBreakdown, TraceSummary


def render_json(summary: TraceSummary) -> str:
    return json.dumps(summary.to_dict(), indent=2, allow_nan=False, ensure_ascii=False)


def render_text(summary: TraceSummary) -> str:
    usage = summary.model_usage
    tools = summary.tools
    activity = summary.activity
    coverage = summary.coverage
    unknown_event_count = sum(coverage.unknown_events.values())
    sections = [
        "Capture",
        f"  Source:          {summary.capture.source}",
        f"  File:            {summary.capture.file}",
        f"  Sessions:        {summary.sessions.count}",
        f"  Prompts:         {summary.sessions.prompts}",
        "",
        "Model usage",
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
        f"  Success rate:    {_percent(tools.successes, tools.calls)}",
        f"  Duration:        {_duration_short(tools.duration_ms)}",
    ]
    if tools.by_name:
        sections.extend(["", _tool_table(tools.by_name)])
    sections.extend(
        [
            "",
            "Activity",
            f"  CLI active time:  {activity.active_time_seconds.get('cli', 0.0):.1f}s",
            f"  User active time: {activity.active_time_seconds.get('user', 0.0):.1f}s",
            f"  Lines added:      {activity.lines_of_code.get('added', 0)}",
            f"  Lines removed:    {activity.lines_of_code.get('removed', 0)}",
            f"  Commits:          {activity.commits}",
            f"  Pull requests:    {activity.pull_requests}",
            "",
            "Coverage",
            f"  Log records:      {coverage.log_records}",
            f"  Metric points:    {coverage.metric_points}",
            f"  Unknown events:   {unknown_event_count}",
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


def _tool_table(rows: tuple[ToolBreakdown, ...]) -> str:
    lines = ["  Tool    Calls  Success  Failures  Avg"]
    for row in rows:
        rate = _percent(row.successes, row.calls)
        average = "n/a" if row.duration_ms_average is None else f"{row.duration_ms_average:.0f}ms"
        lines.append(f"  {row.name:<8}{row.calls:>5}{rate:>8}{row.failures:>10}  {average}")
    return "\n".join(lines)
