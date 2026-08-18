"""Trace collection and summary commands."""

import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from coding_agent_performance.adapters.claude_code.telemetry import SOURCE, ClaudeCodeExportConfig
from coding_agent_performance.trace.capture import CaptureError
from coding_agent_performance.trace.collector import (
    DEFAULT_PORT,
    LOOPBACK_HOST,
    CollectorBindError,
    CollectorStats,
    OtlpHttpCollector,
)
from coding_agent_performance.trace.comparison import compare_summaries
from coding_agent_performance.trace.rendering import (
    render_capture_list,
    render_comparison_json,
    render_comparison_text,
    render_json,
    render_text,
)
from coding_agent_performance.trace.report import TraceSummary
from coding_agent_performance.trace.storage import (
    CaptureListError,
    CaptureStorageError,
    CaptureWriter,
    LatestCaptureError,
    default_captures_dir,
    latest_capture,
    list_captures,
    new_capture_path,
)
from coding_agent_performance.trace.summary import summarize_capture

trace_app = typer.Typer(
    name="trace",
    help="Collect, list, summarize, and compare coding-agent telemetry.",
    no_args_is_help=True,
    add_completion=False,
)
collect_app = typer.Typer(
    name="collect",
    help="Collect telemetry from a supported coding agent.",
    no_args_is_help=True,
    add_completion=False,
)
trace_app.add_typer(collect_app, name="collect")


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


@trace_app.command("list")
def list_captures_command(
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            help="Maximum number of newest captures to print. Must be a positive integer.",
        ),
    ] = None,
) -> None:
    """List local captures without reading their contents."""
    if limit is not None and limit < 1:
        typer.echo("Limit must be a positive integer.", err=True)
        raise typer.Exit(1) from None
    try:
        captures = list_captures(default_captures_dir(), limit=limit)
    except CaptureListError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    typer.echo(render_capture_list(captures))


@trace_app.command("summarize")
def summarize(
    capture: Annotated[
        Path | None,
        typer.Argument(help="CAPT JSONL capture file."),
    ] = None,
    latest: Annotated[
        bool,
        typer.Option("--latest", help="Summarize the newest capture in the default capture directory."),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Summary output format."),
    ] = OutputFormat.TEXT,
) -> None:
    """Summarize a local CAPT capture without sending data anywhere."""
    selected = resolve_summarize_capture(capture, latest=latest)
    summary = summarize_or_fail(selected)
    if output_format is OutputFormat.JSON:
        sys.stdout.write(render_json(summary))
        sys.stdout.write("\n")
        return
    typer.echo(render_text(summary))


@trace_app.command("compare")
def compare(
    baseline: Annotated[
        Path,
        typer.Argument(help="Baseline CAPT JSONL capture file."),
    ],
    candidate: Annotated[
        Path,
        typer.Argument(help="Candidate CAPT JSONL capture file."),
    ],
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Comparison output format."),
    ] = OutputFormat.TEXT,
) -> None:
    """Compare two local CAPT captures without sending data anywhere."""
    if same_capture_file(baseline, candidate):
        summary = summarize_or_fail(baseline)
        result = compare_summaries(summary, summary)
    else:
        result = compare_summaries(summarize_or_fail(baseline), summarize_or_fail(candidate))
    if output_format is OutputFormat.JSON:
        sys.stdout.write(render_comparison_json(result))
        sys.stdout.write("\n")
        return
    typer.echo(render_comparison_text(result))


def summarize_or_fail(path: Path) -> TraceSummary:
    try:
        return summarize_capture(path)
    except CaptureError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    except OSError as exc:
        detail = exc.strerror or str(exc) or "read error"
        typer.echo(f"Invalid capture at {path.name}: {detail}", err=True)
        raise typer.Exit(1) from None


def same_capture_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return False


def resolve_summarize_capture(capture: Path | None, *, latest: bool) -> Path:
    if capture is not None and latest:
        typer.echo("Provide either a capture path or --latest, not both.", err=True)
        raise typer.Exit(1) from None
    if latest:
        try:
            return latest_capture(default_captures_dir())
        except LatestCaptureError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from None
    if capture is None:
        typer.echo("Provide a capture path or --latest.", err=True)
        raise typer.Exit(1) from None
    return capture


@collect_app.command("claude-code")
def collect_claude_code(
    port: Annotated[
        int,
        typer.Option("--port", help="Loopback TCP port for the OTLP HTTP/JSON receiver."),
    ] = DEFAULT_PORT,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="JSONL capture file. Refused if the path already exists."),
    ] = None,
) -> None:
    """Collect Claude Code OpenTelemetry logs and metrics on loopback."""
    if port < 1 or port > 65535:
        typer.echo("Port must be between 1 and 65535.", err=True)
        raise typer.Exit(1)

    restrict_directory = output is None
    capture_path = output.expanduser() if output is not None else new_capture_path(default_captures_dir(), SOURCE)
    writer: CaptureWriter | None = None
    collector: OtlpHttpCollector | None = None
    try:
        writer = CaptureWriter.create(capture_path, restrict_directory=restrict_directory)
        collector = OtlpHttpCollector(host=LOOPBACK_HOST, port=port, writer=writer, source=SOURCE)
        collector.start()
    except (CaptureStorageError, CollectorBindError) as exc:
        if collector is not None:
            collector.close()
        elif writer is not None:
            created = writer.path
            writer.close()
            created.unlink(missing_ok=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None

    config = ClaudeCodeExportConfig(logs_endpoint=collector.logs_url, metrics_endpoint=collector.metrics_url)
    typer.echo(render_started(collector.writer.path, collector.logs_url, collector.metrics_url, config.shell_snippet()))
    serve_error: str | None = None
    try:
        serve_collector(collector)
    except KeyboardInterrupt:
        pass
    except Exception:
        # Serving is a process boundary: never leak request bodies or a traceback.
        serve_error = "Collector failed while serving."
    finally:
        stats = collector.close()
    typer.echo(render_stopped(collector.writer.path, stats))
    if serve_error is not None:
        typer.echo(serve_error, err=True)
        raise typer.Exit(1)


def serve_collector(collector: OtlpHttpCollector) -> None:
    """Block until the collector is interrupted. Extracted for tests."""
    collector.serve_forever()


def render_started(capture_path: Path, logs_url: str, metrics_url: str, snippet: str) -> str:
    return "\n".join(
        [
            "Claude Code telemetry collector started",
            "",
            "Capture:",
            f"  {capture_path}",
            "",
            "Endpoints:",
            f"  logs:    {logs_url}",
            f"  metrics: {metrics_url}",
            "",
            "Start Claude Code in another terminal with:",
            "",
            snippet,
            "",
            "Press Ctrl+C to stop.",
        ]
    )


def render_stopped(capture_path: Path, stats: CollectorStats) -> str:
    return "\n".join(
        [
            "",
            "Collector stopped",
            "",
            "Capture:",
            f"  {capture_path}",
            "",
            "Received:",
            f"  log batches: {stats.log_batches}",
            f"  metric batches: {stats.metric_batches}",
        ]
    )
