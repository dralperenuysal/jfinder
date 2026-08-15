"""Tests for index loading, cost classification and candidate filters."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from jfinder import data as jdata

FIXTURE = Path(__file__).parent / "fixtures" / "journals_mini.parquet"


@pytest.fixture()
def idx() -> pd.DataFrame:
    return jdata.load_index(FIXTURE)


def test_fixture_loads_with_schema(idx: pd.DataFrame) -> None:
    assert len(idx) == 200
    assert set(jdata.REQUIRED_COLUMNS) <= set(idx.columns)
    assert idx["built_at"].nunique() == 1


def test_fixture_covers_all_cost_classes(idx: pd.DataFrame) -> None:
    assert set(idx["cost"]) == set(jdata.COST_CLASSES)


def _row(**overrides: object) -> pd.Series:
    base: dict[str, object] = {
        "openalex_id": "S1",
        "name": "Example Journal",
        "issn_l": "0000-0000",
        "issn": ["0000-0000"],
        "publisher": "Example Publisher",
        "country": "US",
        "topics": ["Oncology"],
        "h_index": 20,
        "citedness_2y": 2.0,
        "works_count": 500,
        "quartile": "Q2",
        "is_oa": False,
        "in_doaj": False,
        "apc_usd": float("nan"),
        "built_at": "2026-08-01",
    }
    base.update(overrides)
    return pd.Series(base)


def test_cost_class_rules() -> None:
    assert jdata.cost_class(_row(is_oa=True, apc_usd=2000.0)) == "oa_paid"
    assert jdata.cost_class(_row(is_oa=True, in_doaj=True, apc_usd=0.0)) == "diamond"
    assert jdata.cost_class(_row(is_oa=True, in_doaj=True)) == "diamond"
    assert jdata.cost_class(_row(is_oa=True)) == "oa_unknown"
    assert jdata.cost_class(_row()) == "subscription"
    # A positive APC wins over DOAJ membership.
    assert jdata.cost_class(_row(is_oa=True, in_doaj=True, apc_usd=2500.0)) == "oa_paid"


def test_null_apc_never_means_free(idx: pd.DataFrame) -> None:
    null_apc = idx[idx["apc_usd"].isna()]
    assert not null_apc.empty
    # Unknown APC is never labeled free: oa_unknown is explicitly not free.
    assert set(null_apc["cost"]) <= {"diamond", "oa_unknown", "subscription"}
    oa_unknown = idx[idx["cost"] == "oa_unknown"]
    assert (~oa_unknown["in_doaj"]).all()


def test_free_to_publish_includes_diamond_and_subscription(idx: pd.DataFrame) -> None:
    out = jdata.apply_filters(idx, cost="free-to-publish")
    assert not out.empty
    assert "oa_paid" not in set(out["cost"])
    assert set(out["cost"]) == {"diamond", "subscription"}


def test_free_to_read(idx: pd.DataFrame) -> None:
    out = jdata.apply_filters(idx, cost="free-to-read")
    assert set(out["cost"]) == {"oa_paid", "diamond", "oa_unknown"}


def test_max_apc_keeps_unknown(idx: pd.DataFrame) -> None:
    out = jdata.apply_filters(idx, max_apc=1000.0)
    paid = out[out["cost"] == "oa_paid"]
    assert (paid["apc_usd"] <= 1000.0).all()
    # A null APC is unknown, not excluded by --max-apc.
    assert out["apc_usd"].isna().any()


def test_quartile_filter(idx: pd.DataFrame) -> None:
    out = jdata.apply_filters(idx, quartiles={"Q1", "Q2"})
    assert not out.empty
    assert set(out["quartile"]) <= {"Q1", "Q2"}
    with pytest.raises(ValueError, match="quartile"):
        jdata.apply_filters(idx, quartiles={"Q5"})


def test_bad_cost_value(idx: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="cost"):
        jdata.apply_filters(idx, cost="expensive")


def test_flag_heuristic() -> None:
    assert jdata.flag(_row(is_oa=True, in_doaj=False, apc_usd=2000.0, h_index=10)) == "unverified"
    assert jdata.flag(_row(is_oa=True, in_doaj=True, apc_usd=2000.0, h_index=10)) is None
    assert jdata.flag(_row(is_oa=True, in_doaj=False, apc_usd=1000.0, h_index=10)) is None
    assert jdata.flag(_row(is_oa=True, in_doaj=False, apc_usd=float("nan"), h_index=10)) is None
    assert jdata.flag(_row(is_oa=False, in_doaj=False, apc_usd=2000.0, h_index=10)) is None
    assert jdata.flag(_row(is_oa=True, in_doaj=False, apc_usd=2000.0, h_index=20)) is None


def test_flagged_hidden_by_default(idx: pd.DataFrame) -> None:
    n_flagged = int(idx["flag"].eq("unverified").sum())
    assert n_flagged > 0
    default = jdata.apply_filters(idx)
    shown = jdata.apply_filters(idx, show_flagged=True)
    assert default["flag"].isna().all()
    assert len(shown) == len(default) + n_flagged


def test_empty_result_raises_readable_error() -> None:
    df = pd.DataFrame([_row(is_oa=True, apc_usd=2000.0)])
    df["cost"] = df.apply(jdata.cost_class, axis=1)
    df["flag"] = df.apply(jdata.flag, axis=1)
    with pytest.raises(jdata.NoCandidatesError, match="No journals"):
        jdata.apply_filters(df, cost="free-to-publish")


def test_load_index_missing_file(tmp_path: Path) -> None:
    with pytest.raises(jdata.DataError, match="not found"):
        jdata.load_index(tmp_path / "nope.parquet")


def test_load_index_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.parquet"
    pd.DataFrame({"name": ["X"]}).to_parquet(path)
    with pytest.raises(jdata.DataError, match="missing columns"):
        jdata.load_index(path)


def test_load_index_bad_parquet(tmp_path: Path) -> None:
    path = tmp_path / "bad.parquet"
    path.write_text("not parquet")
    with pytest.raises(jdata.DataError, match="Cannot read"):
        jdata.load_index(path)
