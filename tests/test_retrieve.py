"""Tests for the BM25 shortlist (AGENTS.md §8)."""

from __future__ import annotations

from pathlib import Path

from jfinder import data as jdata
from jfinder import retrieve as jretrieve

FIXTURE = Path(__file__).parent / "fixtures" / "journals_mini.parquet"


def test_shortlist_size_and_order() -> None:
    idx = jdata.load_index(FIXTURE)
    profile = {"field": "", "subfields": [], "keywords": ["oncology"]}
    out = jretrieve.shortlist(idx, profile, n=40)
    assert len(out) == 40
    assert "_score" in out.columns
    assert out["_score"].is_monotonic_decreasing


def test_shortlist_ranks_matching_topic_first() -> None:
    idx = jdata.load_index(FIXTURE)
    profile = {"field": "", "subfields": [], "keywords": ["oncology"]}
    out = jretrieve.shortlist(idx, profile, n=40)
    top5 = out.head(5)
    assert not top5.empty
    for _, row in top5.iterrows():
        corpus = (str(row["name"]) + " " + " ".join(row["topics"])).lower()
        assert "oncology" in corpus


def test_shortlist_query_builds_from_all_profile_parts() -> None:
    idx = jdata.load_index(FIXTURE)
    profile = {
        "field": "public health",
        "subfields": ["cardiology"],
        "keywords": ["machine learning"],
    }
    out = jretrieve.shortlist(idx, profile, n=10)
    top = out.iloc[0]
    corpus = (str(top["name"]) + " " + " ".join(top["topics"])).lower()
    assert any(term in corpus for term in ("public", "health", "cardiology", "machine", "learning"))
