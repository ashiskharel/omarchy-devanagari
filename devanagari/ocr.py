"""Read an image or a PDF. Text already in a PDF is used before OCR."""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from devanagari.errors import OcrError
from devanagari.paths import cache_dir, tessdata_dir
from devanagari.store import save_last

_IMAGE_CAP = 15_000_000
_PDF_CAP = 8_000_000
_PIXEL_CAP = 12_000_000
_TEXT_ENOUGH = 40


def read_path(path: Path, *, source: str | None = None, psm: str = "3") -> dict:
    path = path.expanduser()
    if not path.is_file():
        raise OcrError(f"No file at {path}.")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(path)
    else:
        _require_tessdata()
        text = _read_image(path, psm)
    return _finish(text, source or str(path))


def read_capture() -> dict | None:
    """Freeze the screen, let the person pick a region, and read it. None if they cancel."""
    _require_tools("hyprpicker", "slurp", "grim")
    _require_tessdata()
    cache_dir().mkdir(parents=True, mode=0o755, exist_ok=True)
    image = cache_dir() / "capture.png"
    picker = subprocess.Popen(
        ["hyprpicker", "-r", "-z"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # The frozen frame has to be up before the region is chosen.
        import time

        time.sleep(0.1)
        try:
            selected = subprocess.run(["slurp"], capture_output=True, text=True, timeout=180, check=False)
        except subprocess.TimeoutExpired as exc:
            raise OcrError("The region picker timed out.") from exc
        geometry = selected.stdout.strip()
        if selected.returncode != 0 or not geometry:
            return None
        shot = subprocess.run(
            ["grim", "-g", geometry, str(image)],
            capture_output=True,
            timeout=15,
            check=False,
        )
    finally:
        if picker.poll() is None:
            picker.terminate()
            try:
                picker.wait(timeout=2)
            except subprocess.TimeoutExpired:
                picker.kill()
    if shot.returncode != 0 or not image.is_file():
        raise OcrError("Could not capture that region.")
    text = _read_image(image, "6")
    return _finish(text, "screen")


def notify(headline: str, body: str = "") -> None:
    command = ["omarchy-notification-send", "-g", "अ", headline]
    if body:
        command.append(body)
    try:
        subprocess.run(command, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return


def _finish(text: str, source: str) -> dict:
    cleaned = text.strip()
    if len(cleaned) > 200_000:
        cleaned = cleaned[:200_000]
    record = {
        "text": cleaned,
        "engine": "tesseract-nep",
        "source": source,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": "" if cleaned else "No text recognized.",
    }
    save_last(record)
    if not cleaned:
        raise OcrError("No text recognized.")
    return record


def _read_pdf(path: Path) -> str:
    if path.stat().st_size > _PDF_CAP:
        raise OcrError("The PDF is larger than 8 MB.")
    text = _run(["pdftotext", "-q", "-f", "1", "-l", "2", str(path), "-"], timeout=20)
    if len(text.strip()) >= _TEXT_ENOUGH:
        return text
    _require_tessdata()
    with tempfile.TemporaryDirectory(prefix="devanagari-") as folder:
        stem = str(Path(folder) / "page")
        subprocess.run(
            ["pdftoppm", "-png", "-f", "1", "-l", "1", "-r", "150", str(path), stem],
            capture_output=True,
            timeout=30,
            check=False,
        )
        image = Path(folder) / "page-1.png"
        if not image.is_file():
            return text
        ocr = _read_image(image, "3")
    return ocr or text


def _read_image(path: Path, psm: str) -> str:
    if path.stat().st_size > _IMAGE_CAP:
        raise OcrError("The image is larger than 15 MB.")
    _reject_huge_bitmap(path)
    return _run(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            "nep+eng",
            "--tessdata-dir",
            str(tessdata_dir()),
            "--oem",
            "1",
            "--psm",
            psm,
            "--dpi",
            "300",
            "-c",
            "preserve_interword_spaces=1",
        ],
        timeout=40,
    )


def _reject_huge_bitmap(path: Path) -> None:
    try:
        result = subprocess.run(
            ["magick", "identify", "-format", "%w %h", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    parts = result.stdout.split()
    if len(parts) < 2:
        return
    try:
        pixels = int(parts[0]) * int(parts[1])
    except ValueError:
        return
    if pixels > _PIXEL_CAP:
        raise OcrError("The image has too many pixels for this machine.")


def _run(command: list[str], timeout: int) -> str:
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise OcrError(f"{command[0]} is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise OcrError(f"{command[0]} took too long.") from exc
    return result.stdout.decode("utf-8", "replace")


def _require_tessdata() -> None:
    path = tessdata_dir() / "nep.traineddata"
    if not path.is_file():
        raise OcrError("Nepali data is not installed. Run devanagari fetch.")


def _require_tools(*names: str) -> None:
    missing = [name for name in names if not _on_path(name)]
    if missing:
        raise OcrError("Missing " + ", ".join(missing) + ".")


def _on_path(name: str) -> bool:
    for folder in os.environ.get("PATH", "").split(":"):
        if folder and (Path(folder) / name).is_file():
            return True
    return False
