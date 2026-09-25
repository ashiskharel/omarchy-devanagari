"""Decide whether this machine may download or load a model. No I/O."""

from __future__ import annotations

import math

# Optional weights must leave this much free RAM before the download starts.
OPTIONAL_HEADROOM_MB = 512
# After a runtime actually loads a model, at least this much RAM must remain.
LOAD_FLOOR_MB = 400
# Nepali tessdata is about 2 MB. It does not use the optional-model headroom.
TESSDATA_FREE_MB = 64


def optional_need_mb(total_bytes: int) -> int:
    return math.ceil((2 * total_bytes) / (1024 * 1024) + OPTIONAL_HEADROOM_MB)


def judge_download(
    available_mb: int,
    total_bytes: int,
    *,
    kind: str,
    published: bool,
    force: bool,
) -> tuple[bool, str]:
    """Return whether a download may start, and the sentence that says why."""
    if not published:
        return False, "Not published yet. There is no file to download."
    if kind == "tessdata":
        if available_mb < TESSDATA_FREE_MB and not force:
            return False, f"{available_mb} MB free. Fetch needs {TESSDATA_FREE_MB} MB free."
        if force and available_mb < TESSDATA_FREE_MB:
            return True, f"Fetch forced with {available_mb} MB free."
        return True, f"{available_mb} MB free. The Nepali data is {total_bytes / (1024 * 1024):.1f} MB."
    need = optional_need_mb(total_bytes)
    if available_mb < need and not force:
        return False, f"{available_mb} MB free. This download needs {need} MB free."
    if force and available_mb < need:
        return True, f"Download forced. {available_mb} MB is free, under the {need} MB check."
    return True, f"{available_mb} MB free covers the {need} MB check."


def judge_run(
    *,
    kind: str,
    stored: bool,
    runtime: bool,
    free_after_load_mb: int | None,
) -> tuple[bool, str]:
    """Return whether reading may use this model."""
    if kind == "tessdata":
        if stored:
            return True, "Installed. This is the reader."
        return False, "Nepali data is not on this machine yet."
    if not stored:
        return False, "Weights are not on this machine."
    if not runtime:
        return False, "ONNX runtime is not installed. This plugin does not install it."
    if free_after_load_mb is None:
        return False, "The weights are stored. They have not been loaded on this machine yet."
    if free_after_load_mb < LOAD_FLOOR_MB:
        return False, f"Loading left {free_after_load_mb} MB free, under the {LOAD_FLOOR_MB} MB floor."
    return True, f"Load left {free_after_load_mb} MB free."
