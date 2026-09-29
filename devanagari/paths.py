"""Cache, tessdata, and config. Nothing here lives inside the plugin directory."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from devanagari.errors import OcrError


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
    if not _is_real_directory(directory):
        raise OcrError("The folder is not a real directory.")
    os.chmod(directory, 0o700)


def write_private(path: Path, text: str) -> None:
    """Replace path with text that other local users cannot read."""
    ensure_private(path.parent)

    def produce(handle) -> None:
        handle.write(text.encode("utf-8"))

    _replace_exclusive(path, produce)


def _is_real_directory(directory: Path) -> bool:
    try:
        info = directory.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode)


def _replace_exclusive(path: Path, produce) -> None:
    """Write through a new file in path's directory, then rename it over path.

    The name is random and opened exclusively, so a symlink already sitting
    at a predictable partial path is not followed. rename replaces a symlink
    at path instead of writing through it.
    """
    if not _is_real_directory(path.parent):
        raise OcrError("The folder is not a real directory.")
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.fchmod(fd, 0o600)
    replaced = False
    try:
        with os.fdopen(fd, "wb") as handle:
            produce(handle)
        os.replace(name, path)
        replaced = True
    finally:
        if not replaced:
            Path(name).unlink(missing_ok=True)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise OcrError("The file is not a regular file.")
    os.chmod(path, 0o600)
