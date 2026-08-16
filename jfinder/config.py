"""User configuration: the stored NVIDIA API key.

The key lives in <user_config_dir>/jfinder/config.json with 0600 permissions.
The NVIDIA_API_KEY environment variable always takes precedence over the
stored value; both are optional (offline mode needs no key).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import platformdirs


def config_dir() -> Path:
    return Path(platformdirs.user_config_dir("jfinder"))


def config_file() -> Path:
    return config_dir() / "config.json"


def get_key() -> str | None:
    """Return the API key: env var first, then the config file."""
    env_key = os.environ.get("NVIDIA_API_KEY")
    if env_key:
        return env_key
    path = config_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("nvidia_api_key") or None
    except (json.JSONDecodeError, OSError):
        return None


def set_key(value: str) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"nvidia_api_key": value}), encoding="utf-8")
    path.chmod(0o600)


def remove_key() -> None:
    try:
        config_file().unlink(missing_ok=True)
    except OSError:
        pass
