"""Regenerate tests/fixtures/journals_mini.parquet (200 deterministic rows).

Run from the repo root:  python tests/fixtures/make_journals_mini.py
No network required; output is deterministic (fixed seed).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from jfinder.data import REQUIRED_COLUMNS

N = 200
SEED = 42
BUILT_AT = "2026-08-01"
TOPICS = [
    "Bioinformatics", "Machine Learning", "Oncology", "Cardiology",
    "Neuroscience", "Public Health", "Materials Science", "Ecology",
]
PUBLISHERS = ["Elsevier", "Springer Nature", "MDPI", "Frontiers", "Wiley", "PLOS", "Sage", "IEEE"]
COUNTRIES = ["US", "GB", "DE", "NL", "CH", "BR", "IN", None]

console = Console()


def main() -> None:
    rng = np.random.default_rng(SEED)
    # 70 oa_paid / 40 diamond / 30 oa_unknown / 60 subscription; quartiles 50 each.
    classes = (["oa_paid"] * 70) + (["diamond"] * 40) + (["oa_unknown"] * 30) + (["subscription"] * 60)
    quartiles = (["Q1"] * 50) + (["Q2"] * 50) + (["Q3"] * 50) + (["Q4"] * 50)
    rng.shuffle(classes)
    rng.shuffle(quartiles)

    h_index_of = {
        "Q1": lambda: int(rng.integers(80, 300)),
        "Q2": lambda: int(rng.integers(40, 79)),
        "Q3": lambda: int(rng.integers(20, 49)),
        "Q4": lambda: int(rng.integers(5, 29)),
    }

    rows: list[dict] = []
    for i in range(N):
        cls, quart = classes[i], quartiles[i]
        topic = TOPICS[rng.integers(0, len(TOPICS))]
        topics = (
            [topic]
            if rng.random() < 0.6
            else [topic, TOPICS[rng.integers(0, len(TOPICS))]]
        )
        is_oa = cls in {"oa_paid", "diamond", "oa_unknown"}
        if cls == "diamond":
            in_doaj, apc = True, float(rng.choice([0.0, np.nan]))
        elif cls == "oa_unknown":
            in_doaj, apc = False, float("nan")
        elif cls == "oa_paid":
            in_doaj, apc = bool(rng.random() < 0.6), float(rng.uniform(500, 3500))
        else:  # subscription (hybrid journals may still list an APC)
            in_doaj = bool(rng.random() < 0.6)
            apc = float(rng.choice([np.nan, np.nan, 2000.0]))
        issn_l = f"0000-{i:04d}"
        publisher = PUBLISHERS[i % len(PUBLISHERS)]
        rows.append(
            {
                "openalex_id": f"S{100000 + i}",
                "name": f"{publisher} Journal of {topic}",
                "issn_l": issn_l,
                "issn": [issn_l],
                "publisher": publisher,
                "country": COUNTRIES[rng.integers(0, len(COUNTRIES))],
                "topics": topics,
                "h_index": h_index_of[quart](),
                "citedness_2y": float(rng.uniform(0, 30)),
                "works_count": int(rng.integers(200, 5000)),
                "quartile": quart,
                "is_oa": is_oa,
                "in_doaj": in_doaj,
                "apc_usd": apc,
                "built_at": BUILT_AT,
            }
        )

    df = pd.DataFrame.from_records(rows)
    # 15 unverified-flag candidates among paid OA rows: not in DOAJ, APC > 1500,
    # low h-index (AGENTS.md §9).
    paid_idx = df.index[df["is_oa"] & (df["apc_usd"] > 0)]
    flagged = rng.choice(paid_idx, size=15, replace=False)
    df.loc[flagged, "in_doaj"] = False
    df.loc[flagged, "h_index"] = rng.integers(2, 14, size=15)
    df.loc[flagged, "apc_usd"] = rng.uniform(1800, 4000, size=15)
    df.loc[flagged, "quartile"] = "Q4"

    out = Path(__file__).resolve().parent / "journals_mini.parquet"
    df[REQUIRED_COLUMNS].to_parquet(out, index=False)
    console.print(f"wrote {out} ({len(df)} rows, {len(flagged)} flagged)")


if __name__ == "__main__":
    main()
