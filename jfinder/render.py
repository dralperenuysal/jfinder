"""Render results: rich table and footers (AGENTS.md §12)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

STALE_AFTER_DAYS = 365
_NAME_WIDTH = 30


def cost_label(row: pd.Series) -> str:
    """Human cost label per AGENTS.md §5. An unknown APC is never 'free'."""
    apc = row["apc_usd"]
    if row["cost"] == "oa_paid":
        return f"OA  ${apc:,.0f}" if pd.notna(apc) else "OA · APC unknown"
    if row["cost"] == "diamond":
        return "Diamond OA"
    if row["cost"] == "oa_unknown":
        return "OA · APC unknown"
    return "Subscription"  # a hybrid OA option is flagged separately


def flags_for(row: pd.Series) -> str:
    """Flag column content (AGENTS.md §9 wording: unverified, not predatory)."""
    parts: list[str] = []
    if row["in_doaj"]:
        parts.append("DOAJ")
    if row["cost"] == "subscription" and pd.notna(row["apc_usd"]) and row["apc_usd"] > 0:
        parts.append("hybrid OA possible")
    if row["flag"] == "unverified":
        parts.append("unverified")
    return ", ".join(parts)


def table_for(results: pd.DataFrame, top_k: int) -> Table:
    """Rich table: # / Journal / Q / Fit / Cost / Flags."""
    table = Table(
        title=f"Top {top_k} target journals",
        header_style="bold",
        title_justify="left",
    )
    for column in ("#", "Journal", "Q", "Fit", "Cost", "Flags"):
        table.add_column(column, no_wrap=(column in {"#", "Q", "Fit"}))
    for position, (_, row) in enumerate(results.head(top_k).iterrows(), start=1):
        name = str(row["name"])
        display = name if len(name) <= _NAME_WIDTH else name[:_NAME_WIDTH - 1] + "…"
        table.add_row(
            str(position),
            display,
            str(row["quartile"]),
            str(row["fit"]),
            cost_label(row),
            flags_for(row),
        )
    return table


def is_stale(built_at: str | None, today: datetime | None = None) -> bool:
    """True when the index is older than 12 months (AGENTS.md §10)."""
    if not built_at:
        return True
    try:
        built = datetime.strptime(built_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    reference = today or datetime.now(timezone.utc)
    return reference - built > timedelta(days=STALE_AFTER_DAYS)


def print_results(
    results: pd.DataFrame,
    top_k: int,
    *,
    removed: int = 0,
    built_at: str | None = None,
) -> None:
    """Print the table plus the permanent footer (AGENTS.md §12)."""
    console.print(table_for(results, top_k))
    if removed:
        console.print(
            f"  ⚠ {removed} candidates removed as unverified "
            "(show with --show-flagged)"
        )
    if is_stale(built_at):
        console.print(
            "  ⚠ Index built more than 12 months ago — "
            "consider rebuilding: python scripts/build_index.py"
        )
    console.print(f"  Index built {built_at} · APC data from OpenAlex/DOAJ, list prices only")
    console.print("  Always verify aims & scope on the journal site before submitting.")
