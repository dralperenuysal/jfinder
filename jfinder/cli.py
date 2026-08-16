"""CLI entry point for jfinder.

All user-facing output goes through rich. JSON mode (later milestone) will
keep rich output on stderr.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from jfinder import __version__
from jfinder import data as jdata
from jfinder import input as jinput
from jfinder import render as jrender
from jfinder import retrieve as jretrieve
from jfinder.data import DataError, JfinderError, index_meta
from jfinder.input import ABSTRACT_TEMPLATE, InputError

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
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit.",
            is_eager=True,
            callback=_version_callback,
        ),
    ] = False,
) -> None:
    """Find target journals for your paper from local OpenAlex data.

    The app callback exists so jfinder is always a click group even when it
    has a single subcommand (typer collapses single-command apps otherwise).
    """


@app.command()
def init(
    path: Annotated[
        Path | None,
        typer.Argument(help="Directory for abstract.md (default: current directory)."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing abstract.md.")
    ] = False,
) -> None:
    """Create an abstract.md template to fill in."""
    directory = path.resolve() if path else Path.cwd()
    target = directory / "abstract.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        console.print(f"[red]{target} already exists.[/red]")
        console.print("  Overwrite: jfinder init --force")
        raise typer.Exit(code=1)
    target.write_text(ABSTRACT_TEMPLATE, encoding="utf-8")
    console.print(f"[green]Created[/green] {target}")
    console.print("  Fill in the template, then run: jfinder find")


@app.command()
def find(
    path: Annotated[
        Path | None, typer.Argument(help="Directory containing abstract.md.")
    ] = None,
    file: Annotated[
        Path | None, typer.Option("-f", "--file", help="Read the abstract from this file.")
    ] = None,
    text: Annotated[
        str | None, typer.Option("-t", "--text", help="Use this abstract text directly.")
    ] = None,
    top_k: Annotated[
        int, typer.Option("-k", "--k", help="Number of journals to show.")
    ] = 5,
    cost: Annotated[
        str, typer.Option("--cost", help="all | free-to-publish | free-to-read.")
    ] = "all",
    max_apc: Annotated[
        float | None, typer.Option("--max-apc", help="Maximum APC in USD.")
    ] = None,
    quartile: Annotated[
        str | None, typer.Option("--quartile", help="Comma-separated quartiles, e.g. Q1,Q2.")
    ] = None,
    show_flagged: Annotated[
        bool, typer.Option("--show-flagged", help="Include journals flagged as unverified.")
    ] = False,
    offline: Annotated[
        bool, typer.Option("--offline", help="Skip the LLM: BM25 over the abstract's own words.")
    ] = False,
) -> None:
    """Suggest up to 5 target journals for the abstract."""
    try:
        abstract_text = jinput.get_text(path, file, text)
    except InputError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    try:
        warnings = jinput.validate(abstract_text)
    except InputError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    for warning in warnings:
        console.print(f"[yellow]{warning}[/yellow]")

    if top_k < 1:
        console.print("[red]-k must be at least 1.[/red]")
        raise typer.Exit(code=1)

    quartiles = {q.strip() for q in quartile.split(",")} if quartile else None
    try:
        index = jdata.load_index()
        flagged_total = int((index["flag"] == "unverified").sum())
        filtered = jdata.apply_filters(
            index, cost=cost, max_apc=max_apc, quartiles=quartiles, show_flagged=show_flagged
        )
    except (JfinderError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    if not offline:
        console.print(
            "[yellow]LLM mode lands in milestone 5 — running the offline search for now.[/yellow]"
        )

    sections = jinput.parse_sections(abstract_text)
    keywords = sections["keywords"]
    profile = {
        "field": str(sections["title"]),
        "subfields": [],
        "keywords": [*keywords, *str(sections["abstract"]).split()],
    }
    short = jretrieve.shortlist(filtered, profile, n=40)
    scores = short["_score"].astype(float)
    top_score = float(scores.max()) if len(scores) else 0.0
    short = short.copy()
    short["fit"] = [
        max(1, round(100 * score / top_score)) if top_score > 0 else 0 for score in scores
    ]
    removed = flagged_total - int((filtered["flag"] == "unverified").sum())
    jrender.print_results(
        short, top_k, removed=removed, built_at=str(filtered["built_at"].iloc[0])
    )


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
