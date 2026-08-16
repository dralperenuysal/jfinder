"""Tests for abstract input: locate, read, validate, parse, and init."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jfinder import input as jinput
from jfinder.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_locate_missing_file_readable_error(tmp_path: Path) -> None:
    with pytest.raises(jinput.InputError, match="abstract.md") as excinfo:
        jinput.locate(tmp_path)
    message = str(excinfo.value)
    assert "jfinder init" in message
    assert "abstract.txt" in message


def test_locate_search_order(tmp_path: Path) -> None:
    (tmp_path / "abstract.txt").write_text("txt", encoding="utf-8")
    assert jinput.locate(tmp_path) == tmp_path / "abstract.txt"
    (tmp_path / "ABSTRACT.md").write_text("md", encoding="utf-8")
    assert jinput.locate(tmp_path) == tmp_path / "abstract.txt"
    (tmp_path / "abstract.md").write_text("md", encoding="utf-8")
    assert jinput.locate(tmp_path) == tmp_path / "abstract.md"


def test_read_any_text_formats(tmp_path: Path) -> None:
    for name in ("abstract.md", "abstract.txt", "abstract.tex", "abstract.rst"):
        path = tmp_path / name
        path.write_text("hello", encoding="utf-8")
        assert jinput.read_any(path) == "hello"


def test_read_any_missing_file(tmp_path: Path) -> None:
    with pytest.raises(jinput.InputError, match="not found"):
        jinput.read_any(tmp_path / "nope.md")


def test_read_any_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "abstract.csv"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(jinput.InputError, match="Unsupported"):
        jinput.read_any(path)


@pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is not None, reason="docs extras installed"
)
def test_pdf_without_extras(tmp_path: Path) -> None:
    path = tmp_path / "abstract.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(jinput.InputError, match=r"jfinder\[docs\]"):
        jinput.read_any(path)


@pytest.mark.skipif(
    importlib.util.find_spec("docx") is not None, reason="docs extras installed"
)
def test_docx_without_extras(tmp_path: Path) -> None:
    path = tmp_path / "abstract.docx"
    path.write_bytes(b"fake")
    with pytest.raises(jinput.InputError, match=r"jfinder\[docs\]"):
        jinput.read_any(path)


def test_validate_placeholder_template() -> None:
    text = (FIXTURES / "abstract_template.md").read_text(encoding="utf-8")
    with pytest.raises(jinput.InputError, match="placeholder"):
        jinput.validate(text)


def test_validate_too_short() -> None:
    text = (FIXTURES / "abstract_short.md").read_text(encoding="utf-8")
    assert len(text.split()) < jinput.MIN_WORDS
    with pytest.raises(jinput.InputError, match="too short"):
        jinput.validate(text)


def test_validate_long_warns_but_continues() -> None:
    text = "# Abstract\n" + " ".join(["word"] * 1200)
    warnings = jinput.validate(text)
    assert warnings
    assert "long" in warnings[0].lower()


def test_validate_good() -> None:
    text = (FIXTURES / "abstract_good.md").read_text(encoding="utf-8")
    assert jinput.validate(text) == []


def test_parse_sections() -> None:
    text = (FIXTURES / "abstract_good.md").read_text(encoding="utf-8")
    sections = jinput.parse_sections(text)
    assert sections["title"]
    assert "sepsis" in str(sections["abstract"]).lower()
    assert sections["keywords"]
    assert sections["study_type"]
    assert sections["notes"]


def test_parse_sections_plain_text_without_headings() -> None:
    text = "This is a plain abstract with no markdown headings at all. " * 5
    sections = jinput.parse_sections(text)
    assert str(sections["abstract"]) == text.strip()
    assert sections["title"] == ""
    assert sections["keywords"] == []
    assert sections["notes"] is None


def test_init_creates_template(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    target = tmp_path / "abstract.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "# Abstract" in content
    assert "# Notes" in content


def test_init_refuses_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "abstract.md"
    target.write_text("custom", encoding="utf-8")
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code != 0
    assert target.read_text(encoding="utf-8") == "custom"
    result = runner.invoke(app, ["init", str(tmp_path), "--force"])
    assert result.exit_code == 0
    assert "# Abstract" in target.read_text(encoding="utf-8")


def test_init_defaults_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "abstract.md").exists()
