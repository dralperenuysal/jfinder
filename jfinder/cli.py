"""CLI entry point for jfinder.

All user-facing output goes through rich. JSON mode (later milestone) will
keep rich output on stderr.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer
from rich.console import Console

from jfinder import __version__
from jfinder import data as jdata
from jfinder import input as jinput
from jfinder import llm as jllm
from jfinder import render as jrender
from jfinder import retrieve as jretrieve
from jfinder.data import DataError, JfinderError, index_meta
from jfinder.input import ABSTRACT_TEMPLATE, InputError
from jfinder.llm import LLMError

app = typer.Typer(
    name="jfinder",
    help="Find target journals for your paper from local OpenAlex data.",
    no_args_is_help=True,
)
console = Console()


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


def _offline_profile(sections: dict[str, object]) -> dict[str, object]:
    """BM25 query from the abstract's own words (AGENTS.md §10)."""
    keywords = sections["keywords"]
    keyword_list = keywords if isinstance(keywords, list) else []
    return {
        "field": str(sections["title"]),
        "subfields": [],
        "keywords": [*keyword_list, *str(sections["abstract"]).split()],
    }


def _with_fit(short: pd.DataFrame) -> pd.DataFrame:
    """Normalize BM25 scores into a 1-100 fit column for display."""
    scores = short["_score"].astype(float)
    top_score = float(scores.max()) if len(scores) else 0.0
    out = short.copy()
    out["fit"] = [
        max(1, round(100 * score / top_score)) if top_score > 0 else 0 for score in scores
    ]
    return out


def _finalize(short: pd.DataFrame, picks: list[dict[str, Any]], top_k: int) -> pd.DataFrame:
    """Build the final table: LLM picks first, BM25 order fills the rest."""
    rows: list[pd.Series] = []
    used: set[int] = set()
    for pick in picks:
        try:
            i = int(pick["i"])
        except (KeyError, TypeError, ValueError):
            continue
        if i < 0 or i >= len(short) or i in used:
            continue
        row = short.iloc[i].copy()
        try:
            row["fit"] = max(0, min(100, int(pick.get("fit", row["fit"]))))
        except (TypeError, ValueError):
            pass
        row["_why"] = str(pick.get("why", "")).strip()
        row["_risk"] = str(pick.get("risk", "")).strip()
        rows.append(row)
        used.add(i)
    for i in range(len(short)):
        if len(rows) >= top_k:
            break
        if i in used:
            continue
        row = short.iloc[i].copy()
        row["_why"] = ""
        row["_risk"] = ""
        rows.append(row)
    return pd.DataFrame(rows)


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
    model: Annotated[
        str | None, typer.Option("--model", help="NIM model id (overrides JFINDER_MODEL).")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Log details, e.g. corrected LLM picks.")
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

    sections = jinput.parse_sections(abstract_text)
    removed = flagged_total - int((filtered["flag"] == "unverified").sum())
    built_at = str(filtered["built_at"].iloc[0])

    if offline:
        short = jretrieve.shortlist(filtered, _offline_profile(sections), n=40)
        jrender.print_results(
            _with_fit(short), top_k, removed=removed, built_at=built_at
        )
        return

    # Online: LLM profile -> BM25 shortlist -> LLM rerank (AGENTS.md §7).
    try:
        llm_profile = jllm.profile(abstract_text, model=model)
        short = jretrieve.shortlist(filtered, llm_profile, n=40)
        short = _with_fit(short)
        candidates = [
            {
                "i": int(position),
                "name": str(row["name"]),
                "topics": list(row["topics"]),
                "quartile": str(row["quartile"]),
                "cost": str(row["cost"]),
            }
            for position, (_, row) in enumerate(short.iterrows())
        ]
        notes = str(sections["notes"] or "")
        reranked = jllm.rerank(llm_profile, candidates, notes, top_k, model=model)
    except LLMError as exc:
        if exc.fatal:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None
        console.print(
            f"[yellow]LLM failed — falling back to offline ranking ({exc})[/yellow]"
        )
        short = jretrieve.shortlist(filtered, _offline_profile(sections), n=40)
        jrender.print_results(
            _with_fit(short), top_k, removed=removed, built_at=built_at
        )
        return

    picks = jllm.sanitize_picks(reranked, len(short))
    if verbose and len(picks) < top_k:
        console.print(
            f"[dim]LLM returned {top_k - len(picks)} invalid or duplicate pick(s); "
            "filled from BM25 order.[/dim]"
        )
    final = _finalize(short, picks, top_k)
    jrender.print_results(
        final, top_k, removed=removed, built_at=built_at, reasons=bool(picks)
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

    console.print(f"Model: {os.environ.get('JFINDER_MODEL', jllm.DEFAULT_MODEL)}")
    status, hint = _key_status()
    console.print(f"NVIDIA_API_KEY: {status}")
    if hint:
        console.print(hint)


if __name__ == "__main__":
    app()
