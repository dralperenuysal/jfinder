"""CLI smoke tests. No network, no API key required."""

from typer.testing import CliRunner

from jfinder.cli import app

runner = CliRunner()


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
