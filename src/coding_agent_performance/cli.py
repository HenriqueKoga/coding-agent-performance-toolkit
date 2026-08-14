"""CAPT command-line interface."""

from importlib.metadata import version
from typing import Annotated

import typer

from coding_agent_performance.diagnostics import collect_diagnostics, render_report

app = typer.Typer(
    name="capt",
    help="Local-first toolkit for measuring and improving coding-agent performance.",
    no_args_is_help=True,
    add_completion=False,
)


def package_version() -> str:
    """Return the installed distribution version."""
    return version("coding-agent-performance-toolkit")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"capt {package_version()}")
        raise typer.Exit(0)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Coding Agent Performance Toolkit (CAPT)."""


@app.command()
def doctor() -> None:
    """Check local environment requirements for CAPT."""
    report = collect_diagnostics()
    typer.echo(render_report(report))
    raise typer.Exit(0 if report.ok else 1)
