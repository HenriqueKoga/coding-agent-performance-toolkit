"""Trace collection commands."""

from contextlib import suppress
from pathlib import Path
from typing import Annotated

import typer

from coding_agent_performance.adapters.claude_code.telemetry import SOURCE, ClaudeCodeExportConfig
from coding_agent_performance.trace.collector import (
    DEFAULT_PORT,
    LOOPBACK_HOST,
    CollectorBindError,
    CollectorStats,
    OtlpHttpCollector,
)
from coding_agent_performance.trace.storage import (
    CaptureStorageError,
    CaptureWriter,
    default_captures_dir,
    new_capture_path,
)

trace_app = typer.Typer(
    name="trace",
    help="Collect coding-agent telemetry locally.",
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
    with suppress(KeyboardInterrupt):
        serve_collector(collector)
    stats = collector.close()
    typer.echo(render_stopped(collector.writer.path, stats))


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
