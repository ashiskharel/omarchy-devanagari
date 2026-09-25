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


def ensure_private(directory: Path) -> None:
    """Create a cache directory only this user can search. An existing 0755 directory is tightened."""
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)


def write_private(path: Path, text: str) -> None:
    """Replace path with text that other local users cannot read."""
    ensure_private(path.parent)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(text, encoding="utf-8")
    os.chmod(partial, 0o600)
    os.replace(partial, path)
    os.chmod(path, 0o600)
