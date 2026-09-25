"""Where downloaded files and the last reading live."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from devanagari.catalog import card_bytes
from devanagari.errors import OcrError
from devanagari.net import download
from devanagari.paths import cache_dir, config_file, last_path, model_dir, tessdata_dir


def support_url() -> str:
    path = config_file()
    if not path.exists():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    url = str(raw.get("supportUrl") or "").strip()
    if url.startswith("https://") or url.startswith("http://"):
        return url
    return ""


def file_ready(path: Path, sha256: str, size: int) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != size:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == sha256


def model_stored(card: dict) -> bool:
    if not card["published"]:
        return False
    root = _root_for(card)
    return all(file_ready(root / item["name"], item["sha256"], int(item["bytes"])) for item in card["files"])


def fetch_model(card: dict) -> str:
    """Download every pinned file for a card. Returns a short sentence."""
    if not card["published"]:
        raise OcrError(f"{card['name']} is not published yet. There is no file to download.")
    root = _root_for(card)
    root.mkdir(parents=True, mode=0o755, exist_ok=True)
    pending = [item for item in card["files"] if not file_ready(root / item["name"], item["sha256"], int(item["bytes"]))]
    if not pending:
        return f"{card['name']} is already on this machine."
    for item in pending:
        download(item["url"], root / item["name"], item["sha256"], int(item["bytes"]))
    if card["kind"] == "tessdata":
        _link_system_languages(root)
    return f"Downloaded {card['name']} ({card_bytes(card) / (1024 * 1024):.1f} MB)."


def save_last(record: dict) -> None:
    cache_dir().mkdir(parents=True, mode=0o755, exist_ok=True)
    path = last_path()
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(partial, path)


def load_last() -> dict:
    path = last_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def copy_text(text: str) -> None:
    import subprocess

    try:
        subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OcrError(f"Could not copy to the clipboard: {exc}") from exc


def _root_for(card: dict) -> Path:
    if card["kind"] == "tessdata":
        return tessdata_dir()
    return model_dir(card["id"])


def _link_system_languages(tessdata: Path) -> None:
    system = Path("/usr/share/tessdata")
    for name in ("eng.traineddata", "osd.traineddata"):
        dest = tessdata / name
        if dest.exists() or dest.is_symlink():
            continue
        src = system / name
        if not src.is_file():
            raise OcrError(f"System tessdata is missing {name}.")
        dest.symlink_to(src)


