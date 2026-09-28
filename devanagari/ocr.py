"""Read an image or a PDF. Text already in a PDF is used before OCR."""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from devanagari.errors import OcrError
from devanagari.paths import cache_dir, ensure_private, tessdata_dir
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
    """Let the person drag a box, then read it. None if they cancel."""
    _require_tools("slurp", "grim")
    _require_tessdata()
    ensure_private(cache_dir())
    image = cache_dir() / "capture.png"
    if not _wait_for_panel_to_close():
        _remember("The panel was still covering the screen, so the crosshair could not show.")
        return None
    notify("Drag a box around the text", "It works over a terminal, a browser, or a document.")
    try:
        selected = subprocess.run(
            ["slurp", "-b", "00000099", "-c", "ffffffff", "-w", "2"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _remember("The crosshair waited, and no box was dragged.")
        raise OcrError("The crosshair waited, and no box was dragged.") from exc
    geometry = selected.stdout.strip()
    if selected.returncode != 0 or not geometry:
        detail = (selected.stderr or "").strip()
        message = detail or "No region was selected."
        _remember(message)
        return None
    if _selection_too_small(geometry):
        _remember("Drag a box around the text. A click does not select a line.")
        return None
    shot = subprocess.run(
        ["grim", "-g", geometry, str(image)],
        capture_output=True,
        timeout=15,
        check=False,
    )
    if shot.returncode != 0 or not image.is_file():
        detail = (shot.stderr or b"").decode("utf-8", "replace").strip()
        message = detail or "Could not capture that region."
        _remember(message)
        raise OcrError(message)
    os.chmod(image, 0o600)
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


def _wait_for_panel_to_close() -> bool:
    """The plugin panel is a full-screen overlay. slurp cannot show through it."""
    for _ in range(40):
        if "omarchy-keyboard-panel" not in _layer_text():
            return True
        time.sleep(0.05)
    subprocess.run(
        ["omarchy-shell", "ashis.devanagari", "close"],
        capture_output=True,
        timeout=3,
        check=False,
    )
    for _ in range(20):
        if "omarchy-keyboard-panel" not in _layer_text():
            return True
        time.sleep(0.05)
    return False


def _layer_text() -> str:
    try:
        result = subprocess.run(["hyprctl", "layers"], capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout


def _selection_too_small(geometry: str) -> bool:
    """slurp prints 'x,y wxh'. A bare click is a speck, not a line of text."""
    try:
        _origin, size = geometry.split()
        width, height = size.lower().split("x", 1)
        return int(width) < 8 or int(height) < 8
    except (ValueError, IndexError):
        return False


def _remember(message: str) -> None:
    save_last({
        "text": "",
        "engine": "tesseract-nep",
        "source": "screen",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": message,
    })


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
    pixels = _header_pixels(path)
    if pixels is None:
        raise OcrError("Could not read the image size.")
    if pixels > _PIXEL_CAP:
        raise OcrError("The image has too many pixels for this machine.")


def _header_pixels(path: Path) -> int | None:
    """Width times height from the file header. The pixel data is not decoded."""
    with path.open("rb") as handle:
        head = handle.read(32)
        if len(head) < 10:
            return None
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            if len(head) < 24 or head[12:16] != b"IHDR":
                return None
            width, height = struct.unpack(">II", head[16:24])
            return _pixels(width, height)
        if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
            width, height = struct.unpack_from("<HH", head, 6)
            return _pixels(width, height)
        if head.startswith(b"BM") and len(head) >= 26:
            width, height = struct.unpack_from("<ii", head, 18)
            return _pixels(width, abs(height))
        if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
            extra = handle.read(16)
            return _webp_pixels(head + extra)
        if head.startswith(b"\xff\xd8"):
            rest = handle.read(_IMAGE_CAP)
            return _jpeg_pixels(head + rest)
    return None


def _pixels(width: int, height: int) -> int | None:
    if width <= 0 or height <= 0:
        return None
    return width * height


def _webp_pixels(buf: bytes) -> int | None:
    if len(buf) < 20:
        return None
    kind = buf[12:16]
    if kind == b"VP8X" and len(buf) >= 30:
        width = 1 + int.from_bytes(buf[24:27], "little")
        height = 1 + int.from_bytes(buf[27:30], "little")
        return _pixels(width, height)
    if kind == b"VP8 " and len(buf) >= 30 and buf[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(buf[26:28], "little") & 0x3FFF
        height = int.from_bytes(buf[28:30], "little") & 0x3FFF
        return _pixels(width, height)
    if kind == b"VP8L" and len(buf) >= 25 and buf[20] == 0x2F:
        bits = int.from_bytes(buf[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return _pixels(width, height)
    return None


def _jpeg_pixels(data: bytes) -> int | None:
    i = 2
    n = len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            return None
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            return None
        marker = data[i]
        i += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if i + 2 > n:
            return None
        length = int.from_bytes(data[i : i + 2], "big")
        if length < 2 or i + length > n:
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                return None
            height = int.from_bytes(data[i + 3 : i + 5], "big")
            width = int.from_bytes(data[i + 5 : i + 7], "big")
            return _pixels(width, height)
        if marker == 0xDA:
            return None
        i += length
    return None


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
