"""devanagari: a machine check, then Nepali text from a picture, a PDF, or the screen."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from devanagari.catalog import find_card, load_cards
from devanagari.errors import OcrError
from devanagari.gate import judge_download
from devanagari.hardware import format_report, memory_mb, report
from devanagari.ocr import notify, read_capture, read_geometry, read_path
from devanagari.score import evaluate, format_rows
from devanagari.store import copy_text, fetch_model, load_last


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devanagari",
        description="Read Devanagari on this machine. The hardware check comes first.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    hardware = sub.add_parser("hardware", help="show what this machine can run")
    hardware.add_argument("--json", action="store_true")
    status = sub.add_parser("status", help="machine check, engines, and the last reading as JSON")
    status.add_argument("--json", action="store_true", default=True)

    sub.add_parser("models", help="list the engines")

    fetch = sub.add_parser("fetch", help="download Nepali data, or a model the machine check allows")
    fetch.add_argument("--model", default="tesseract-nep")
    fetch.add_argument("--force", action="store_true", help="pass the memory check only; the checksum still applies")

    read = sub.add_parser("read", help="read an image or a PDF")
    read.add_argument("path", type=Path)
    read.add_argument("--copy", action="store_true")
    read.add_argument("--json", action="store_true")
    read.add_argument("--psm", default="3")

    capture = sub.add_parser("capture", help="read a region of the screen")
    capture.add_argument("--geometry", help="box already chosen, as 'x,y wxh'")
    capture.add_argument("--json", action="store_true")
    capture.add_argument("--no-copy", action="store_true")

    evaluate_cmd = sub.add_parser("eval", help="score the sample pages")
    evaluate_cmd.add_argument("--dir", type=Path)

    last = sub.add_parser("last", help="print the last reading")
    last.add_argument("--copy", action="store_true")
    last.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        return _run(args)
    except OcrError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    if args.command in ("hardware", "status"):
        payload = report()
        if args.command == "status" or args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(format_report(payload))
        binary = payload["hardware"]["tesseract"]
        return 0 if not binary.startswith("Tesseract is not") else 1
    if args.command == "models":
        for card in load_cards():
            state = "published" if card["published"] else "not published"
            print(f"{card['id']}: {card['name']} ({state})")
        return 0
    if args.command == "fetch":
        return _fetch(args.model, args.force)
    if args.command == "read":
        record = read_path(args.path, psm=args.psm)
        return _emit(record, as_json=args.json, copy=args.copy, notify_user=False)
    if args.command == "capture":
        record = read_geometry(args.geometry) if args.geometry else read_capture()
        if record is None:
            print("Selection cancelled.")
            return 0
        return _emit(record, as_json=args.json, copy=not args.no_copy, notify_user=not args.no_copy)
    if args.command == "eval":
        print(format_rows(evaluate(args.dir)))
        return 0
    if args.command == "last":
        record = load_last()
        if not record:
            raise OcrError("No reading yet.")
        return _emit(record, as_json=args.json, copy=args.copy, notify_user=False)
    return 2


def _fetch(model_id: str, force: bool) -> int:
    card = find_card(model_id)
    _, available = memory_mb()
    allowed, why = judge_download(
        available,
        sum(int(item["bytes"]) for item in card["files"]),
        kind=card["kind"],
        published=bool(card["published"]),
        force=force,
    )
    if not allowed:
        raise OcrError(why)
    if force and "forced" in why:
        print(why, file=sys.stderr)
    print(fetch_model(card))
    return 0


def _emit(record: dict, *, as_json: bool, copy: bool, notify_user: bool) -> int:
    text = str(record.get("text") or "")
    if copy and text:
        copy_text(text)
    if notify_user and text:
        notify("Copied Devanagari text", text.splitlines()[0][:80])
    if as_json:
        print(json.dumps(record, ensure_ascii=False))
    else:
        print(text)
    return 0 if text else 1


if __name__ == "__main__":
    raise SystemExit(main())
