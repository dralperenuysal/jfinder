"""CLI smoke tests. No network, no API key required."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from jfinder import data as jdata
from jfinder import llm as jllm
from jfinder.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"
GOOD_TEXT = (FIXTURES / "abstract_good.md").read_text(encoding="utf-8")


@pytest.fixture()
def fixture_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI at the 200-row test fixture instead of the real index."""
    monkeypatch.setattr(jdata, "INDEX_PATH", FIXTURES / "journals_mini.parquet")


@pytest.fixture()
def no_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that attempts an HTTP request."""

    def bomb(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"Unexpected HTTP request: {args} {kwargs}")

    monkeypatch.setattr("urllib.request.urlopen", bomb)


def test_info_succeeds_without_index() -> None:
    """`jfinder info` works before the index is built (milestone 1)."""
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "jfinder" in result.stdout
    assert "Index" in result.stdout
    assert "Model" in result.stdout
    assert "NVIDIA_API_KEY" in result.stdout


def test_version_flag() -> None:
    """`jfinder --version` prints the version and exits cleanly."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "jfinder 0.1.0" in result.stdout


def test_find_offline_end_to_end(fixture_index: None, no_http: None) -> None:
    result = runner.invoke(app, ["find", "-t", GOOD_TEXT, "--offline"])
    assert result.exit_code == 0
    assert "Top 5 target journals" in result.stdout
    assert "Always verify aims & scope" in result.stdout
    assert "Index built 2026-08-01" in result.stdout


def test_find_offline_without_api_key(fixture_index: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    result = runner.invoke(app, ["find", "-t", GOOD_TEXT, "--offline"])
    assert result.exit_code == 0


def test_find_cost_filter_free_to_publish(fixture_index: None, no_http: None) -> None:
    result = runner.invoke(
        app, ["find", "-t", GOOD_TEXT, "--offline", "--cost", "free-to-publish"]
    )
    assert result.exit_code == 0
    assert "OA  $" not in result.stdout
    assert ("Diamond OA" in result.stdout) or ("Subscription" in result.stdout)


def test_find_flagged_hidden_then_shown(fixture_index: None, no_http: None) -> None:
    default = runner.invoke(app, ["find", "-t", GOOD_TEXT, "--offline"])
    shown = runner.invoke(app, ["find", "-t", GOOD_TEXT, "--offline", "--show-flagged"])
    assert default.exit_code == 0
    assert shown.exit_code == 0
    assert "candidates removed" in default.stdout
    assert "candidates removed" not in shown.stdout


def test_find_missing_input_readable(fixture_index: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["find", "--offline"])
    assert result.exit_code != 0
    assert "No abstract.md found" in result.stdout
    assert "jfinder init" in result.stdout
    assert "Traceback" not in result.stdout


def _mini_row(built_at: str) -> dict[str, object]:
    return {
        "openalex_id": "S1",
        "name": "Example Journal",
        "issn_l": "0000-0000",
        "issn": ["0000-0000"],
        "publisher": "Example Publisher",
        "country": "US",
        "topics": ["Oncology"],
        "h_index": 30,
        "citedness_2y": 2.0,
        "works_count": 500,
        "quartile": "Q4",
        "is_oa": True,
        "in_doaj": True,
        "apc_usd": 2000.0,
        "built_at": built_at,
    }


def test_find_empty_result_readable(no_http: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mini = tmp_path / "mini.parquet"
    pd.DataFrame([_mini_row("2026-08-01")]).to_parquet(mini)
    monkeypatch.setattr(jdata, "INDEX_PATH", mini)
    result = runner.invoke(
        app, ["find", "-t", GOOD_TEXT, "--offline", "--cost", "free-to-publish"]
    )
    assert result.exit_code != 0
    assert "No journals" in result.stdout
    assert "Traceback" not in result.stdout


def test_find_stale_index_warns(no_http: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mini = tmp_path / "mini.parquet"
    pd.DataFrame([_mini_row("2019-01-01")]).to_parquet(mini)
    monkeypatch.setattr(jdata, "INDEX_PATH", mini)
    result = runner.invoke(app, ["find", "-t", GOOD_TEXT, "--offline"])
    assert result.exit_code == 0
    assert "more than 12 months ago" in result.stdout


# --- online (LLM) path, mocked: no network, no real API key (AGENTS.md §14) ---

PROFILE = {
    "field": "Medicine",
    "subfields": ["Intensive Care"],
    "study_type": "retrospective cohort",
    "keywords": ["sepsis", "icu"],
    "audience": "clinicians",
    "novelty_1_5": 3,
    "summary": "a sepsis model",
}


def test_find_online_shows_llm_reasons(fixture_index: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(jllm, "profile", lambda text, model=None: PROFILE)

    def fake_rerank(profile: dict, candidates: list, notes: str | None, k: int, model: str | None = None) -> dict:
        return {"picks": [{"i": 0, "fit": 91, "why": "topical fit", "risk": "low"}]}

    monkeypatch.setattr(jllm, "rerank", fake_rerank)
    result = runner.invoke(app, ["find", "-t", GOOD_TEXT])
    assert result.exit_code == 0
    assert "topical fit" in result.stdout
    assert "fit 91" in result.stdout
    assert "low" in result.stdout


def test_find_online_missing_key_is_fatal(fixture_index: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    result = runner.invoke(app, ["find", "-t", GOOD_TEXT])
    assert result.exit_code != 0
    assert "NVIDIA_API_KEY is not set" in result.stdout
    assert "https://build.nvidia.com" in result.stdout


def test_find_online_llm_failure_falls_back_to_offline(
    fixture_index: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    def boom(text: str, model: str | None = None) -> dict:
        raise jllm.LLMError("model returned nothing usable")

    monkeypatch.setattr(jllm, "profile", boom)
    result = runner.invoke(app, ["find", "-t", GOOD_TEXT])
    assert result.exit_code == 0
    assert "falling back to offline ranking" in result.stdout
    assert "Top 5 target journals" in result.stdout


def test_find_online_invalid_picks_filled_from_bm25(
    fixture_index: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(jllm, "profile", lambda text, model=None: PROFILE)

    def fake_rerank(profile: dict, candidates: list, notes: str | None, k: int, model: str | None = None) -> dict:
        return {"picks": [{"i": 999, "fit": 90, "why": "w", "risk": "r"}]}

    monkeypatch.setattr(jllm, "rerank", fake_rerank)
    result = runner.invoke(app, ["find", "-t", GOOD_TEXT, "--verbose"])
    assert result.exit_code == 0
    assert "Top 5 target journals" in result.stdout
    assert "filled from BM25 order" in result.stdout
