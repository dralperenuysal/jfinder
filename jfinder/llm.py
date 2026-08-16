"""NVIDIA NIM LLM layer: profile extraction and candidate reranking (AGENTS.md §7).

The LLM never selects journals. It only (a) extracts a structured profile
from the abstract and (b) reranks candidates that local BM25 search already
found. Candidates always come from the local data file.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import OpenAI

#: Default NIM model id; overridable via JFINDER_MODEL or --model (AGENTS.md §7).
#: The NIM catalog changes often; deepseek-v3.1 was retired, v4-flash is its successor.
DEFAULT_MODEL = "deepseek-ai/deepseek-v4-flash-0731"
BASE_URL = "https://integrate.api.nvidia.com/v1"
TIMEOUT = 60

PROFILE_KEYS = (
    "field",
    "subfields",
    "study_type",
    "keywords",
    "audience",
    "novelty_1_5",
    "summary",
)


class LLMError(RuntimeError):
    """LLM returned something unusable, or its key is missing."""

    def __init__(self, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal


def model_id() -> str:
    return os.getenv("JFINDER_MODEL", DEFAULT_MODEL)


def client() -> OpenAI:
    """NIM client; a missing key is a fatal, user-facing error (AGENTS.md §7)."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LLMError(
            "NVIDIA_API_KEY is not set.\n"
            "  Get a free key: https://build.nvidia.com  →  Get API Key\n"
            "  export NVIDIA_API_KEY=nvapi-...",
            fatal=True,
        )
    return OpenAI(base_url=BASE_URL, api_key=api_key, timeout=TIMEOUT)


def parse_json(raw: str) -> dict[str, Any]:
    """Parse model output tolerantly: drop <think> blocks and markdown fences."""
    text = raw.split("</think>")[-1]
    text = text.replace("```json", "").replace("```", "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model did not return JSON.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {exc}") from exc


def _complete(
    cli: OpenAI,
    system: str,
    user: str,
    *,
    temperature: float,
    max_tokens: int,
    model: str | None,
) -> str:
    """One chat completion with timeout and a single network retry (AGENTS.md §16)."""
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            response = cli.chat.completions.create(
                model=model or model_id(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        # Broad catch on purpose: any SDK/network failure must retry once and
        # end up as a friendly LLMError, never a raw traceback (AGENTS.md §16).
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(2)
    raise LLMError(f"LLM call failed after one retry: {last_exc}")


def profile(text: str, cli: OpenAI | None = None, model: str | None = None) -> dict[str, Any]:
    """Extract a structured profile from the abstract (AGENTS.md §7).

    On a JSON parse error, retry once with temperature=0; if that also fails,
    raise LLMError so the caller can fall back to the offline ranking.
    """
    cli = cli or client()
    system = (
        "You extract a structured profile from a paper abstract for journal "
        "matching. Return only JSON with exactly these keys: field (string), "
        "subfields (list of strings), study_type (string), keywords (list of "
        "strings, 4-8 items), audience (string), novelty_1_5 (integer 1-5), "
        "summary (one sentence)."
    )
    user = f"Abstract:\n{text}"
    raw = _complete(cli, system, user, temperature=0.2, max_tokens=1024, model=model)
    try:
        data = parse_json(raw)
    except LLMError:
        raw = _complete(cli, system, user, temperature=0.0, max_tokens=1024, model=model)
        data = parse_json(raw)
    missing = [key for key in PROFILE_KEYS if key not in data]
    if missing:
        raise LLMError(f"Profile is missing keys: {', '.join(missing)}")
    return data


def rerank(
    profile_data: dict[str, Any],
    candidates: list[dict[str, Any]],
    notes: str | None,
    k: int,
    cli: OpenAI | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Rerank BM25 candidates; the model must pick only from the given list."""
    cli = cli or client()
    system = (
        "You rerank a shortlist of candidate journals for a paper. Strict "
        "rules: choose ONLY from the given list, never invent journal names, "
        "and the i field must be the exact index of the journal in the list. "
        f"Return only JSON: {{\"picks\": [{{\"i\": int, \"fit\": int, \"why\": str, \"risk\": str}}]}} "
        f"with exactly {k} picks, fit between 0 and 100, why and risk each at most one sentence."
    )
    user = json.dumps(
        {
            "profile": profile_data,
            "candidates": candidates,
            "notes": notes or "",
            "k": k,
        },
        ensure_ascii=False,
    )
    raw = _complete(cli, system, user, temperature=0.3, max_tokens=2048, model=model)
    try:
        return parse_json(raw)
    except LLMError:
        raw = _complete(cli, system, user, temperature=0.0, max_tokens=2048, model=model)
        return parse_json(raw)


def sanitize_picks(data: dict[str, Any], n_candidates: int) -> list[dict[str, Any]]:
    """Drop picks with out-of-range or duplicate indices (AGENTS.md §7)."""
    seen: set[int] = set()
    clean: list[dict[str, Any]] = []
    for pick in data.get("picks", []):
        try:
            i = int(pick["i"])
        except (KeyError, TypeError, ValueError):
            continue
        if i < 0 or i >= n_candidates or i in seen:
            continue
        seen.add(i)
        clean.append({**pick, "i": i})
    return clean
