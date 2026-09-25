"""Model cards shipped with the plugin. Weights are not in the repository."""

from __future__ import annotations

import json
from pathlib import Path

from devanagari.errors import OcrError

_CARDS = Path(__file__).with_name("cards.json")


def load_cards() -> list[dict]:
    try:
        raw = json.loads(_CARDS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OcrError(f"The model list could not be read: {exc}") from exc
    models = raw.get("models")
    if not isinstance(models, list) or not models:
        raise OcrError("The model list is empty.")
    for card in models:
        _check_card(card)
    return models


def find_card(model_id: str) -> dict:
    for card in load_cards():
        if card["id"] == model_id:
            return card
    known = ", ".join(card["id"] for card in load_cards())
    raise OcrError(f"Unknown model {model_id}. Known models: {known}.")


def card_bytes(card: dict) -> int:
    return sum(int(item["bytes"]) for item in card["files"])


def _check_card(card: dict) -> None:
    for key in ("id", "name", "kind", "published", "files", "note"):
        if key not in card:
            raise OcrError(f"A model card is missing {key}.")
    if card["kind"] not in ("tessdata", "onnx-rec"):
        raise OcrError(f"{card['id']} has an unknown kind.")
    if not isinstance(card["files"], list):
        raise OcrError(f"{card['id']} has no file list.")
    if card["published"] and not card["files"]:
        raise OcrError(f"{card['id']} is marked published and has no file.")
    if not card["published"] and card["files"]:
        raise OcrError(f"{card['id']} is unpublished and still lists a file.")
    for item in card["files"]:
        url = str(item.get("url") or "")
        digest = str(item.get("sha256") or "")
        if not url.startswith("https://"):
            raise OcrError(f"{card['id']} has a file that is not an https URL.")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise OcrError(f"{card['id']} has a file without a sha256.")
        if int(item.get("bytes") or 0) <= 0:
            raise OcrError(f"{card['id']} has a file without a byte cap.")
