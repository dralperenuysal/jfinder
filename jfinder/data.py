"""Load the bundled journal index and apply candidate filters.

Data contract: AGENTS.md §4. Cost classification and flags: AGENTS.md §5, §9.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pandas as pd

#: Bundled journal index; produced by scripts/build_index.py.
INDEX_PATH: Path = Path(str(resources.files("jfinder") / "data")) / "journals.parquet"

#: Columns the code relies on (AGENTS.md §4). Missing ones raise a readable error.
REQUIRED_COLUMNS: list[str] = [
    "openalex_id",
    "name",
    "issn_l",
    "issn",
    "publisher",
    "country",
    "topics",
    "h_index",
    "citedness_2y",
    "works_count",
    "quartile",
    "is_oa",
    "in_doaj",
    "apc_usd",
    "built_at",
]

COST_CLASSES: frozenset[str] = frozenset(
    {"oa_paid", "diamond", "oa_unknown", "subscription"}
)

#: --cost filter groups (AGENTS.md §5).
COST_GROUPS: dict[str, set[str]] = {
    "all": set(COST_CLASSES),
    "free-to-publish": {"diamond", "subscription"},
    "free-to-read": {"oa_paid", "diamond", "oa_unknown"},
    "diamond": {"diamond"},
}

QUARTILES: frozenset[str] = frozenset({"Q1", "Q2", "Q3", "Q4"})


class JfinderError(RuntimeError):
    """Base class for expected, user-facing errors (no raw tracebacks)."""


class DataError(JfinderError):
    """The index file is missing or does not match the data contract."""


class NoCandidatesError(JfinderError):
    """No journals remain after filtering."""


def cost_class(row: pd.Series) -> str:
    """Classify one journal row (AGENTS.md §5).

    A null apc_usd means *unknown*, never free.
    """
    if row.is_oa and row.apc_usd and row.apc_usd > 0:
        return "oa_paid"  # OA, author pays
    if row.is_oa and row.in_doaj and (pd.isna(row.apc_usd) or row.apc_usd == 0):
        return "diamond"  # OA, nobody pays
    if row.is_oa:
        return "oa_unknown"  # OA but APC unknown
    return "subscription"  # reader pays; hybrid OA option may exist


def flag(row: pd.Series) -> str | None:
    """Heuristic unverified-publisher flag (AGENTS.md §9).

    This is a warning, not an accusation: OA, not in DOAJ, high APC,
    low h-index.
    """
    if not row.in_doaj and row.is_oa and (row.apc_usd or 0) > 1500 and row.h_index < 15:
        return "unverified"
    return None


def load_index(path: Path | None = None) -> pd.DataFrame:
    """Read the index, validate the schema and add derived columns (cost, flag)."""
    index_path = path or INDEX_PATH
    if not index_path.exists():
        raise DataError(
            f"Journal index not found: {index_path}\n"
            "  Build it with: python scripts/build_index.py"
        )
    try:
        df = pd.read_parquet(index_path)
    except Exception as exc:
        raise DataError(f"Cannot read journal index ({index_path}): {exc}") from exc
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise DataError(f"Journal index is missing columns: {', '.join(missing)}")
    df["cost"] = df.apply(cost_class, axis=1)
    df["flag"] = df.apply(flag, axis=1)
    return df


def apply_filters(
    df: pd.DataFrame,
    *,
    cost: str = "all",
    max_apc: float | None = None,
    quartiles: set[str] | None = None,
    show_flagged: bool = False,
) -> pd.DataFrame:
    """Apply cost -> quartile -> max-APC -> flag filters, in that order.

    Raises NoCandidatesError with a readable message if nothing survives.
    """
    if cost not in COST_GROUPS:
        raise ValueError(
            f"Unknown cost filter: {cost!r} (choose from {', '.join(sorted(COST_GROUPS))})"
        )
    out = df[df["cost"].isin(COST_GROUPS[cost])]
    if quartiles:
        unknown = quartiles - QUARTILES
        if unknown:
            raise ValueError(f"Unknown quartile(s): {', '.join(sorted(unknown))}")
        out = out[out["quartile"].isin(quartiles)]
    if max_apc is not None:
        # A null APC means unknown, not excluded by --max-apc.
        out = out[out["apc_usd"].isna() | (out["apc_usd"] <= max_apc)]
    if not show_flagged:
        out = out[out["flag"].isna()]
    if out.empty:
        raise NoCandidatesError(
            "No journals match these filters. Loosen --cost, --quartile or "
            "--max-apc, or try --show-flagged."
        )
    return out


def index_meta(path: Path | None = None) -> tuple[int, str] | None:
    """Return (journal_count, built_at) for the index, or None if not built."""
    index_path = path or INDEX_PATH
    if not index_path.exists():
        return None
    try:
        meta = pd.read_parquet(index_path, columns=["built_at"])
        if meta.empty:
            raise DataError(f"Journal index is empty: {index_path}")
        return len(meta), str(meta["built_at"].iloc[0])
    except DataError:
        raise
    except Exception as exc:
        raise DataError(f"Cannot read journal index ({index_path}): {exc}") from exc
