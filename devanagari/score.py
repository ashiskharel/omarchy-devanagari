"""Character error rate for the local sample pages."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from devanagari.errors import OcrError
from devanagari.ocr import read_path
from devanagari.paths import samples_dir


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFC", text.strip())
    return re.sub(r"\s+", " ", folded)


def character_error(expected: str, actual: str) -> float:
    left = normalize(expected)
    right = normalize(actual)
    if not left:
        return 0.0 if not right else 1.0
    return _distance(left, right) / len(left)


def evaluate(folder: Path | None = None) -> list[dict]:
    root = folder or samples_dir()
    texts = sorted(root.glob("*.txt"))
    if not texts:
        raise OcrError(f"No sample text in {root}.")
    rows = []
    for expected_path in texts:
        image = _image_for(expected_path)
        expected = expected_path.read_text(encoding="utf-8")
        if image is None:
            rows.append({"name": expected_path.stem, "cer": None, "error": "no image"})
            continue
        try:
            record = read_path(image, source=image.name)
        except OcrError as exc:
            rows.append({"name": expected_path.stem, "cer": None, "error": str(exc)})
            continue
        rate = character_error(expected, record["text"])
        rows.append({"name": expected_path.stem, "cer": rate, "actual": record["text"], "error": ""})
    return rows


def format_rows(rows: list[dict]) -> str:
    lines = []
    scored = [row["cer"] for row in rows if isinstance(row.get("cer"), float)]
    for row in rows:
        if row.get("error"):
            lines.append(f"{row['name']}: {row['error']}")
        else:
            lines.append(f"{row['name']}: {row['cer']:.3f}")
    if scored:
        mean = sum(scored) / len(scored)
        lines.append(f"mean: {mean:.3f}")
    return "\n".join(lines)


def _image_for(text_path: Path) -> Path | None:
    for suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".pdf"):
        candidate = text_path.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def _distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, char in enumerate(left, start=1):
        current = [i]
        for j, other in enumerate(right, start=1):
            cost = 0 if char == other else 1
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]
