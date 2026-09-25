"""Cache, tessdata, and config. Nothing here lives inside the plugin directory."""

from __future__ import annotations

import os
from pathlib import Path


def _under(env: str, default: str, *parts: str) -> Path:
    root = Path(os.environ.get(env) or Path.home() / default)
    return root.joinpath(*parts)


def cache_dir() -> Path:
    return _under("XDG_CACHE_HOME", ".cache", "omarchy-devanagari")


def data_dir() -> Path:
    return _under("XDG_DATA_HOME", ".local/share", "omarchy-devanagari")


def config_file() -> Path:
    return _under("XDG_CONFIG_HOME", ".config", "omarchy-devanagari", "config.json")


def tessdata_dir() -> Path:
    return data_dir() / "tessdata"


def model_dir(model_id: str) -> Path:
    return data_dir() / "models" / model_id


def last_path() -> Path:
    return cache_dir() / "last.json"


def probe_path() -> Path:
    return cache_dir() / "probe.json"


def samples_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "samples"
