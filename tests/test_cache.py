"""Tests for the result cache (AGENTS.md §11)."""

from __future__ import annotations

from pathlib import Path

from jfinder import cache as jcache


def test_cache_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("platformdirs.user_cache_dir", lambda name: str(tmp_path))
    key = jcache.profile_key("abstract text", "model-a")
    assert jcache.get("profiles", key) is None
    jcache.put("profiles", key, {"field": "Medicine"})
    assert jcache.get("profiles", key) == {"field": "Medicine"}


def test_key_depends_on_abstract_and_model() -> None:
    assert jcache.profile_key("a", "m") != jcache.profile_key("b", "m")
    assert jcache.profile_key("a", "m") != jcache.profile_key("a", "n")
    assert jcache.profile_key("a", "m") == jcache.profile_key("a", "m")


def test_rerank_key_depends_on_filters() -> None:
    base = ("abstract", "model", "all", None, False, 5)
    assert jcache.rerank_key(*base) != jcache.rerank_key("abstract", "model", "free-to-publish", None, False, 5)
    assert jcache.rerank_key(*base) != jcache.rerank_key("abstract", "model", "all", 1000.0, False, 5)
    assert jcache.rerank_key(*base) != jcache.rerank_key("abstract", "model", "all", None, True, 5)
    assert jcache.rerank_key(*base) != jcache.rerank_key("abstract", "model", "all", None, False, 3)


def test_corrupt_cache_file_is_a_miss(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("platformdirs.user_cache_dir", lambda name: str(tmp_path))
    key = jcache.profile_key("abstract", "model")
    path = tmp_path / "profiles" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert jcache.get("profiles", key) is None


def test_put_silently_ignores_os_errors(monkeypatch, tmp_path: Path) -> None:
    # A cache dir that cannot be created must not crash the tool.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setattr(jcache, "cache_dir", lambda: blocker / "jfinder")
    jcache.put("profiles", "key", {"x": 1})  # must not raise
