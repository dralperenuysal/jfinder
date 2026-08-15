"""CLI entry point for jfinder.

All user-facing output goes through rich. JSON mode (later milestone) will
keep rich output on stderr.
"""

from __future__ import annotations

import os

import typer
from rich.console import Console

from jfinder import __version__
from jfinder.data import DataError, index_meta

app = typer.Typer(
    name="jfinder",
    help="Find target journals for your paper from local OpenAlex data.",
    no_args_is_help=True,
)
console = Console()

#: Default NIM model id; overridable via JFINDER_MODEL or --model (find).
DEFAULT_MODEL = "deepseek-ai/deepseek-v3.1"


def _key_status() -> tuple[str, str]:
    """Return (status, hint) for the NVIDIA API key."""
    if os.environ.get("NVIDIA_API_KEY"):
        return "set", ""
    return (
        "not set",
        "  Get a free key: https://build.nvidia.com  →  Get API Key\n"
        + "  export NVIDIA_API_KEY=nvapi-...",
    )


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"jfinder {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """Find target journals for your paper from local OpenAlex data.

    The app callback exists so jfinder is always a click group even when it
    has a single subcommand (typer collapses single-command apps otherwise).
    """


@app.command()
def info() -> None:
    """Show index date, journal count, model and API key status."""
    console.print(f"[bold]jfinder[/bold] v{__version__}")

    try:
        meta = index_meta()
    except DataError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("  Rebuild it: python scripts/build_index.py")
    else:
        if meta is None:
            console.print("Index: not built yet")
            console.print("  Build it: python scripts/build_index.py")
        else:
            count, built = meta
            console.print(f"Index: {count:,} journals (built {built})")

    console.print(f"Model: {os.environ.get('JFINDER_MODEL', DEFAULT_MODEL)}")
    status, hint = _key_status()
    console.print(f"NVIDIA_API_KEY: {status}")
    if hint:
        console.print(hint)


if __name__ == "__main__":
    app()
