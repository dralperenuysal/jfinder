"""Tests for the stored API key config (env var always wins)."""

from __future__ import annotations

from pathlib import Path

from jfinder import config as jconfig


def test_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jconfig, "config_dir", lambda: tmp_path)
    assert jconfig.get_key() is None
    jconfig.set_key("nvapi-x")
    assert jconfig.get_key() == "nvapi-x"
    jconfig.remove_key()
    assert jconfig.get_key() is None


def test_env_var_precedence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jconfig, "config_dir", lambda: tmp_path)
    jconfig.set_key("stored-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "from-env")
    assert jconfig.get_key() == "from-env"
    monkeypatch.delenv("NVIDIA_API_KEY")
    assert jconfig.get_key() == "stored-key"


def test_corrupt_config_file_is_a_miss(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jconfig, "config_dir", lambda: tmp_path)
    jconfig.config_file().write_text("{not json", encoding="utf-8")
    assert jconfig.get_key() is None


def test_config_file_is_private(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jconfig, "config_dir", lambda: tmp_path)
    jconfig.set_key("nvapi-x")
    mode = jconfig.config_file().stat().st_mode & 0o777
    assert mode == 0o600


def test_remove_key_when_absent_is_safe(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(jconfig, "config_dir", lambda: tmp_path)
    jconfig.remove_key()  # must not raise
