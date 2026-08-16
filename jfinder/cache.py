"""Result cache: abstract hash -> profile / rerank (AGENTS.md §11).

Profile and rerank are cached separately: changing filters reruns the rerank
but never repeats the profile call. --no-cache skips both.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import platformdirs


def cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("jfinder"))


def profile_key(abstract: str, model: str) -> str:
    return hashlib.sha256(f"{abstract}\n{model}".encode()).hexdigest()


def rerank_key(abstract: str, model: str, *filters: object) -> str:
    parts = "|".join(str(f) for f in (abstract, model, *filters))
    return hashlib.sha256(parts.encode()).hexdigest()


def get(namespace: str, key: str) -> dict[str, Any] | None:
    """Return the cached JSON value, or None on miss / corrupt file."""
    path = cache_dir() / namespace / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def put(namespace: str, key: str, value: dict[str, Any]) -> None:
    """Write the value to the cache; failures are silent (cache is optional)."""
    path = cache_dir() / namespace / f"{key}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
