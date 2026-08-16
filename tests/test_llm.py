"""Tests for the NIM LLM layer, fully mocked — no network, no API key (AGENTS.md §14)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from jfinder import llm as jllm


def _fake_client(text: str) -> SimpleNamespace:
    """A fake OpenAI client returning `text` and recording every call."""

    def create(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )

    calls: list[dict[str, object]] = []
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), calls=calls)


# --- parse_json robustness (AGENTS.md §7) ---


def test_parse_json_strips_think_block_and_fences() -> None:
    raw = "<think>some reasoning</think>\n```json\n{\"field\": \"Medicine\"}\n```"
    assert jllm.parse_json(raw) == {"field": "Medicine"}


def test_parse_json_plain_with_surrounding_text() -> None:
    assert jllm.parse_json('prefix {"a": 1} suffix') == {"a": 1}


def test_parse_json_missing_json_raises() -> None:
    with pytest.raises(jllm.LLMError, match="did not return JSON"):
        jllm.parse_json("no json here at all")


def test_parse_json_invalid_json_raises() -> None:
    with pytest.raises(jllm.LLMError, match="invalid JSON"):
        jllm.parse_json('{"broken": }')


# --- profile ---


def test_profile_returns_schema_and_retries_parse_at_temperature_zero() -> None:
    good = (
        '{"field": "Medicine", "subfields": ["Intensive Care"], '
        '"study_type": "retrospective cohort", '
        '"keywords": ["sepsis", "icu", "deep learning"], '
        '"audience": "clinicians", "novelty_1_5": 3, "summary": "s"}'
    )
    fake = _fake_client(good)
    data = jllm.profile("an abstract", cli=fake, model="test-model")
    assert data["field"] == "Medicine"
    assert data["keywords"] == ["sepsis", "icu", "deep learning"]
    assert fake.calls[0]["model"] == "test-model"
    assert fake.calls[0]["temperature"] == 0.2


def test_profile_retries_once_with_temperature_zero_on_bad_json() -> None:
    fake = _fake_client("first")
    fake.calls = []  # reset

    class Flaky:
        def __init__(self, inner: SimpleNamespace) -> None:
            self.inner = inner
            self.count = 0

        def create(self, **kwargs: object) -> SimpleNamespace:
            self.count += 1
            self.inner.calls.append(kwargs)
            if self.count == 1:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
                )
            content = (
                '{"field": "f", "subfields": [], "study_type": "s", "keywords": ["a"], '
                '"audience": "a", "novelty_1_5": 1, "summary": "s"}'
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    flaky = Flaky(fake)
    fake.chat.completions.create = flaky.create  # type: ignore[attr-defined]
    data = jllm.profile("an abstract", cli=fake)
    assert data["field"] == "f"
    assert flaky.count == 2
    assert fake.calls[1]["temperature"] == 0.0


def test_profile_missing_keys_raises() -> None:
    fake = _fake_client('{"field": "Medicine"}')
    with pytest.raises(jllm.LLMError, match="missing keys"):
        jllm.profile("an abstract", cli=fake)


# --- rerank + pick sanitizing (AGENTS.md §7) ---


def test_rerank_prompt_includes_candidates_and_notes() -> None:
    fake = _fake_client('{"picks": [{"i": 0, "fit": 90, "why": "w", "risk": "r"}]}')
    candidates = [{"i": 0, "name": "Journal A"}]
    data = jllm.rerank({"field": "f"}, candidates, "some notes", 1, cli=fake)
    assert data["picks"][0]["i"] == 0
    sent = fake.calls[0]["messages"][1]["content"]
    assert "Journal A" in sent
    assert "some notes" in sent


def test_sanitize_picks_drops_out_of_range_and_duplicates() -> None:
    data = {
        "picks": [
            {"i": 0, "fit": 90},
            {"i": 99, "fit": 80},  # out of range
            {"i": 0, "fit": 70},   # duplicate
            {"i": "2", "fit": 60},  # string index is fine
            {"i": -1, "fit": 50},  # negative
            {"fit": 40},           # missing i
        ]
    }
    clean = jllm.sanitize_picks(data, 5)
    assert [pick["i"] for pick in clean] == [0, 2]


# --- key handling ---


def test_client_missing_key_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(jllm.LLMError) as excinfo:
        jllm.client()
    assert excinfo.value.fatal
    assert "NVIDIA_API_KEY" in str(excinfo.value)
    assert "https://build.nvidia.com" in str(excinfo.value)


def test_profile_without_key_raises_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(jllm.LLMError) as excinfo:
        jllm.profile("an abstract")
    assert excinfo.value.fatal
