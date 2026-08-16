"""Render results: rich table and footers (AGENTS.md §12)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

STALE_AFTER_DAYS = 365
_NAME_WIDTH = 48


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
    table.add_column("#", no_wrap=True)
    table.add_column("Journal", no_wrap=True, overflow="ellipsis", max_width=_NAME_WIDTH)
    for column in ("Q", "Fit"):
        table.add_column(column, no_wrap=True)
    for column in ("Cost", "Flags"):
        table.add_column(column)
    for position, (_, row) in enumerate(results.head(top_k).iterrows(), start=1):
        table.add_row(
            str(position),
            str(row["name"]),
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


def to_json(
    results: pd.DataFrame,
    top_k: int,
    *,
    removed: int = 0,
    built_at: str | None = None,
) -> str:
    """Same data as the table, as JSON for stdout (--json, AGENTS.md §10)."""
    journals: list[dict[str, object]] = []
    for position, (_, row) in enumerate(results.head(top_k).iterrows(), start=1):
        why = str(row.get("_why", "")).strip()
        risk = str(row.get("_risk", "")).strip()
        journals.append(
            {
                "rank": position,
                "name": str(row["name"]),
                "quartile": str(row["quartile"]),
                "fit": int(row["fit"]),
                "cost": str(row["cost"]),
                "cost_label": cost_label(row),
                "flags": flags_for(row),
                "why": why or None,
                "risk": risk or None,
            }
        )
    payload: dict[str, object] = {
        "journals": journals,
        "removed_flagged": removed,
        "built_at": built_at,
        "stale": is_stale(built_at),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _print_footer(removed: int, built_at: str | None) -> None:
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
    console.print(
        "  Always verify aims & scope and current fees on the journal site before submitting."
    )


def print_results(
    results: pd.DataFrame,
    top_k: int,
    *,
    removed: int = 0,
    built_at: str | None = None,
    reasons: bool = False,
) -> None:
    """Print the table, LLM rationale blocks and the permanent footer (AGENTS.md §12)."""
    console.print(table_for(results, top_k))
    if reasons:
        for position, (_, row) in enumerate(results.head(top_k).iterrows(), start=1):
            why = str(row.get("_why", "")).strip()
            risk = str(row.get("_risk", "")).strip()
            if not why and not risk:
                continue
            name = str(row["name"])
            console.print(f"\n{position}. {name:<48} fit {row['fit']}")
            if why:
                console.print(f"   ▸ {why}")
            if risk:
                console.print(f"   ⚠ {risk}")
    _print_footer(removed, built_at)


def print_report(
    results: pd.DataFrame,
    top_k: int,
    *,
    removed: int = 0,
    built_at: str | None = None,
    reasons: bool = False,
) -> None:
    """Plain-text list report: full journal names, no table truncation."""
    console.print(f"Top {top_k} target journals\n")
    for position, (_, row) in enumerate(results.head(top_k).iterrows(), start=1):
        console.print(f"{position}. {row['name']}")
        console.print(
            f"   {row['quartile']} · Fit {row['fit']} · "
            f"{cost_label(row)}" + (f" · {flags}" if (flags := flags_for(row)) else "")
        )
        if reasons:
            why = str(row.get("_why", "")).strip()
            risk = str(row.get("_risk", "")).strip()
            if why:
                console.print(f"   ▸ {why}")
            if risk:
                console.print(f"   ⚠ {risk}")
        console.print("")
    _print_footer(removed, built_at)
