"""Build jfinder/data/journals.parquet from OpenAlex /sources.

Maintenance script — never called at runtime (AGENTS.md §3).

Usage:
    python scripts/build_index.py [--mailto you@example.com] [--out path.parquet]

Data contract: AGENTS.md §4. OpenAlex data is CC0 (see DATA.md).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jfinder.data import REQUIRED_COLUMNS

API = "https://api.openalex.org/sources"
#: Same filter as AGENTS.md §4: journals only, enough works to matter.
FILTER = "type:journal,works_count:>100"
SELECT = (
    "id,display_name,issn_l,issn,host_organization_name,country_code,"
    "topics,summary_stats,works_count,is_oa,is_in_doaj,apc_usd"
)
PER_PAGE = 200
TIMEOUT = 30
POLITE_DELAY = 0.15

console = Console()
OUT_PATH = Path(__file__).resolve().parent.parent / "jfinder" / "data" / "journals.parquet"


def get_json(url: str, params: dict[str, str]) -> dict:
    """GET a JSON API with timeout and a single retry (AGENTS.md §16)."""
    full = f"{url}?{urllib.parse.urlencode(params)}"
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(
                full,
                headers={"User-Agent": "jfinder-build/0.1 (mailto:dralperenuysal@gmail.com)"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            console.print(f"[yellow]Attempt {attempt} failed ({exc}); retrying...[/yellow]")
            time.sleep(2)
    raise RuntimeError(f"GET failed after one retry: {full} ({last_exc})")


def fetch_sources(mailto: str) -> list[dict]:
    """Fetch all journal sources via OpenAlex cursor pagination."""
    params: dict[str, str] = {
        "filter": FILTER,
        "select": SELECT,
        "per-page": str(PER_PAGE),
        "mailto": mailto,
        "cursor": "*",
    }
    rows: list[dict] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("· {task.fields[journals]} journals"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        page_task: TaskID | None = None
        while True:
            data = get_json(API, params)
            rows.extend(data.get("results", []))
            if page_task is None:
                total_pages = -(-int(data["meta"]["count"]) // PER_PAGE)
                page_task = progress.add_task(
                    f"Fetching {data['meta']['count']:,} journals from OpenAlex",
                    total=total_pages,
                    journals="0",
                )
            progress.update(page_task, advance=1, journals=f"{len(rows):,}")
            cursor = data["meta"].get("next_cursor")
            if not cursor:
                progress.update(page_task, completed=total_pages)
                break
            params["cursor"] = cursor
            time.sleep(POLITE_DELAY)
    return rows


def _field_quartile(group: pd.DataFrame) -> pd.Series:
    """Within-field quartile: qcut(4) on h_index (AGENTS.md §4)."""
    if group["h_index"].nunique() < 4:
        return pd.Series("Q4", index=group.index)
    try:
        q = pd.qcut(group["h_index"], 4, labels=["Q4", "Q3", "Q2", "Q1"])
    except ValueError:  # duplicate bin edges — fall back to percentile buckets
        pct = group["h_index"].rank(pct=True)
        q = pd.cut(
            pct,
            [0, 0.25, 0.5, 0.75, 1.0],
            labels=["Q4", "Q3", "Q2", "Q1"],
            include_lowest=True,
        )
    return q.astype(str)


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Convert OpenAlex source rows into the AGENTS.md §4 schema."""
    records = [
        {
            "openalex_id": str(r["id"]).rsplit("/", 1)[-1],
            "name": r.get("display_name"),
            "issn_l": r.get("issn_l"),
            "issn": list(r.get("issn") or []),
            "publisher": r.get("host_organization_name"),
            "country": r.get("country_code"),
            "topics": [t["display_name"] for t in (r.get("topics") or [])],
            "h_index": (r.get("summary_stats") or {}).get("h_index"),
            "citedness_2y": (r.get("summary_stats") or {}).get("2yr_mean_citedness"),
            "works_count": r.get("works_count"),
            "is_oa": bool(r.get("is_oa")),
            "in_doaj": bool(r.get("is_in_doaj")),
            "apc_usd": r.get("apc_usd"),
        }
        for r in rows
    ]
    df = pd.DataFrame.from_records(records)
    df["apc_usd"] = pd.to_numeric(df["apc_usd"], errors="coerce")
    df["h_index"] = pd.to_numeric(df["h_index"], errors="coerce").fillna(0).astype(int)
    df["citedness_2y"] = pd.to_numeric(df["citedness_2y"], errors="coerce")
    df["works_count"] = pd.to_numeric(df["works_count"], errors="coerce").fillna(0).astype(int)

    # Primary topic = first listed topic (ordered by works count in OpenAlex).
    df["_primary"] = df["topics"].apply(lambda t: t[0] if t else "Other")
    quartile = pd.Series("Q4", index=df.index, dtype=str)
    for idx in df.groupby("_primary").groups.values():
        quartile.loc[idx] = _field_quartile(df.loc[idx])
    df["quartile"] = quartile
    df = df.drop(columns=["_primary"])

    df["built_at"] = datetime.now(timezone.utc).date().isoformat()
    return df[REQUIRED_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the jfinder journal index.")
    parser.add_argument("--mailto", default="dralperenuysal@gmail.com",
                        help="Mailto for the OpenAlex polite pool.")
    parser.add_argument("--out", type=Path, default=OUT_PATH,
                        help="Output parquet path.")
    args = parser.parse_args()

    console.print(f"Fetching OpenAlex /sources (filter={FILTER!r}) ...")
    rows = fetch_sources(args.mailto)
    console.print(f"Fetched {len(rows):,} journals; building frame ...")
    df = rows_to_frame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    console.print(f"Wrote {len(df):,} journals to {args.out}")
    console.print(f"built_at={df['built_at'].iloc[0]} · columns={list(df.columns)}")


if __name__ == "__main__":
    main()
