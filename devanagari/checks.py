"""Plain checks for the machine-check rules and the PDF text path."""

from __future__ import annotations

import os
import struct
import tempfile
import zlib
from pathlib import Path

from devanagari.errors import OcrError
from devanagari.gate import judge_download, judge_run, optional_need_mb
from devanagari.ocr import read_path
from devanagari.score import character_error


def main() -> int:
    os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="devanagari-check-")
    assert optional_need_mb(8 * 1024 * 1024) == 528
    allowed, _ = judge_download(1400, 2_189_424, kind="tessdata", published=True, force=False)
    assert allowed
    refused, why = judge_download(30, 2_189_424, kind="tessdata", published=True, force=False)
    assert not refused and "64" in why
    allowed, why = judge_download(1400, 7_935_595, kind="onnx-rec", published=True, force=False)
    assert allowed and "528" in why
    refused, why = judge_download(400, 7_935_595, kind="onnx-rec", published=True, force=False)
    assert not refused and "528" in why
    refused, _ = judge_download(4000, 0, kind="onnx-rec", published=False, force=True)
    assert not refused
    run, _ = judge_run(kind="onnx-rec", stored=True, runtime=False, free_after_load_mb=None)
    assert not run
    run, why = judge_run(kind="onnx-rec", stored=True, runtime=True, free_after_load_mb=200)
    assert not run and "400" in why
    from devanagari.ocr import _selection_too_small

    assert _selection_too_small("10,10 2x2")
    assert not _selection_too_small("10,10 240x40")
    assert character_error("नेपाल", "नेपाल") == 0
    assert character_error("नेपाल", "नेपा") < 0.3

    pdf = _text_pdf("Hello Nepal this page already has a text layer.")
    record = read_path(pdf, source="check")
    assert "Hello Nepal" in record["text"]

    huge = _png_header(40_000, 40_000)
    try:
        read_path(huge, source="check")
        raise AssertionError("a 40k by 40k PNG header must be refused")
    except OcrError as exc:
        assert "pixels" in str(exc)

    unknown = Path(tempfile.NamedTemporaryFile(prefix="devanagari-", suffix=".png", delete=False).name)
    unknown.write_bytes(b"not-an-image")
    try:
        read_path(unknown, source="check")
        raise AssertionError("an image whose size cannot be read must be refused")
    except OcrError as exc:
        assert "size" in str(exc)

    _assert_pdf_bounds()
    _assert_pdftotext_is_capped()
    _assert_capture_leaves_other_pickers()
    _assert_writes_do_not_follow_symlinks()
    _assert_untrusted_text_is_plain()

    print("checks ok")
    return 0


def _assert_pdf_bounds() -> None:
    import devanagari.ocr as ocr

    huge = _text_pdf("Hi", width=2000, height=2000)
    calls: list[str] = []
    real_run = ocr.subprocess.run

    def spy(command, **kwargs):
        calls.append(command[0])
        return real_run(command, **kwargs)

    ocr.subprocess.run = spy
    try:
        read_path(huge, source="check")
        raise AssertionError("a 2000pt page must be refused before rendering")
    except OcrError as exc:
        assert "pixels" in str(exc)
    finally:
        ocr.subprocess.run = real_run
    assert "pdftoppm" not in calls
    assert "pdfinfo" in calls

    blank = Path(tempfile.NamedTemporaryFile(prefix="devanagari-", suffix=".pdf", delete=False).name)
    blank.write_bytes(b"%PDF-1.4\nnot a page\n")
    calls.clear()
    ocr.subprocess.run = spy
    try:
        read_path(blank, source="check")
        raise AssertionError("a PDF whose page size cannot be read must be refused")
    except OcrError as exc:
        assert "page size" in str(exc)
    finally:
        ocr.subprocess.run = real_run
    assert "pdftoppm" not in calls

    small = _text_pdf("Hi", width=300, height=100)
    assert ocr._pdf_page_pixels(small) <= ocr._PIXEL_CAP


def _assert_pdftotext_is_capped() -> None:
    import sys
    import time

    import devanagari.ocr as ocr

    script = (
        "import sys, time; "
        "sys.stdout.buffer.write(b'x' * 2000000); "
        "sys.stdout.buffer.flush(); "
        "time.sleep(30)"
    )
    started = time.monotonic()
    text = ocr._read_capped(
        [sys.executable, "-c", script],
        timeout=10,
        limit=ocr._TEXT_CAP,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 8, elapsed
    assert len(text.encode("utf-8")) <= ocr._TEXT_CAP
    assert len(text) == ocr._TEXT_CAP


def _assert_capture_leaves_other_pickers() -> None:
    import devanagari.ocr as ocr

    assert "pkill" not in Path(ocr.__file__).read_text()
    real_run = ocr.subprocess.run
    commands: list[list[str]] = []

    def spy(command, **kwargs):
        commands.append(list(command))
        class Result:
            returncode = 0 if command[:2] == ["pgrep", "-x"] and command[2] == "slurp" else 1
            stdout = b"99\n" if returncode == 0 else b""
            stderr = b""
        return Result()

    ocr.subprocess.run = spy
    real_tools = ocr._require_tools
    real_tess = ocr._require_tessdata
    real_private = ocr.ensure_private
    real_wait = ocr._wait_for_panel_to_close
    ocr._require_tools = lambda *_names: None
    ocr._require_tessdata = lambda: None
    ocr.ensure_private = lambda _path: None
    ocr._wait_for_panel_to_close = lambda: True
    try:
        assert ocr.read_capture() is None
    finally:
        ocr.subprocess.run = real_run
        ocr._require_tools = real_tools
        ocr._require_tessdata = real_tess
        ocr.ensure_private = real_private
        ocr._wait_for_panel_to_close = real_wait
    assert all(command[0] != "pkill" for command in commands)
    assert ["pgrep", "-x", "slurp"] in commands


def _assert_writes_do_not_follow_symlinks() -> None:
    import hashlib
    import stat

    import devanagari.net as net
    import devanagari.ocr as ocr
    from devanagari.paths import write_private

    root = Path(tempfile.mkdtemp(prefix="devanagari-link-"))
    canary = root / "canary"
    canary.write_bytes(b"secret")
    canary.chmod(0o644)
    folder = root / "cache"
    folder.mkdir(mode=0o700)
    planted = folder / "last.json.partial"
    planted.symlink_to(canary)
    target = folder / "last.json"
    target.symlink_to(canary)

    write_private(target, "kept\n")

    assert canary.read_bytes() == b"secret"
    assert stat.S_IMODE(canary.stat().st_mode) == 0o644
    assert planted.is_symlink()
    assert not target.is_symlink()
    assert target.read_text(encoding="utf-8") == "kept\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600

    outside = root / "outside"
    outside.mkdir(mode=0o700)
    nested = root / "via-link"
    nested.symlink_to(outside)
    try:
        write_private(nested / "note.json", "nope")
        raise AssertionError("a symlinked directory must be refused")
    except OcrError as exc:
        assert "directory" in str(exc)
    assert not (outside / "note.json").exists()

    image = folder / "capture.png"
    image.symlink_to(canary)
    real_run = ocr.subprocess.run
    real_read = ocr._read_image

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"png-bytes")
        class Result:
            returncode = 0
            stderr = b""
        return Result()

    ocr.subprocess.run = fake_run
    ocr._read_image = lambda path, psm: "ok"
    try:
        record = ocr._read_geometry("10,10 40x20", image)
    finally:
        ocr.subprocess.run = real_run
        ocr._read_image = real_read
    assert record["text"] == "ok"
    assert canary.read_bytes() == b"secret"
    assert stat.S_IMODE(canary.stat().st_mode) == 0o644
    assert not image.is_symlink()
    assert image.read_bytes() == b"png-bytes"
    assert stat.S_IMODE(image.stat().st_mode) == 0o600

    body = b"model-bytes"
    dest = folder / "model.onnx"
    partial = folder / "model.onnx.partial"
    partial.symlink_to(canary)
    dest.symlink_to(canary)

    class Body:
        def __init__(self):
            self.headers = {"Content-Length": str(len(body))}
            self.offset = 0

        def read(self, size):
            chunk = body[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request, timeout):
            return Body()

    real_opener = net.urllib.request.build_opener
    net.urllib.request.build_opener = lambda *args, **kwargs: Opener()
    try:
        net.download(
            "https://example.invalid/model.onnx",
            dest,
            hashlib.sha256(body).hexdigest(),
            cap=len(body),
        )
    finally:
        net.urllib.request.build_opener = real_opener
    assert canary.read_bytes() == b"secret"
    assert partial.is_symlink()
    assert not dest.is_symlink()
    assert dest.read_bytes() == body
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600


def _assert_untrusted_text_is_plain() -> None:
    root = Path(__file__).resolve().parents[1]
    panel = (root / "Panel.qml").read_text()
    bar = (root / "BarWidget.qml").read_text()
    assert panel.count("Text {") == panel.count("textFormat: Text.PlainText")
    assert panel.count("Text {") >= 9
    assert "StdioCollector" not in panel
    assert "Text.AutoText" not in panel
    assert "Text.StyledText" not in panel
    assert "Text.RichText" not in panel
    assert '["capture", "--quiet"]' in panel
    assert '["last", "--copy", "--quiet"]' in panel
    assert "streamCap: 32000" in panel
    assert bar.count("Text {") == 0
    main = (root / "devanagari" / "__main__.py").read_text()
    assert 'notify("Copied Devanagari text", "The line is on the clipboard.")' in main
    assert "splitlines()[0]" not in main
    source = (root / "devanagari" / "ocr.py").read_text()
    image = source.split("def _read_image", 1)[1].split("\ndef ", 1)[0]
    assert "_read_capped(" in image
    assert "capture_output" not in image
    assert "def _run(" not in source


def _png_header(width: int, height: int) -> Path:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    body = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")
    handle = tempfile.NamedTemporaryFile(prefix="devanagari-", suffix=".png", delete=False)
    handle.write(body)
    handle.close()
    return Path(handle.name)


def _text_pdf(words: str, width: int = 300, height: int = 100) -> Path:
    stream = f"BT /F1 12 Tf 20 50 Td ({words}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>".encode("ascii"),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{number} 0 obj\n".encode("ascii"))
        body.extend(obj)
        body.extend(b"\nendobj\n")
    xref = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    body.extend(
        f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    handle = tempfile.NamedTemporaryFile(prefix="devanagari-", suffix=".pdf", delete=False)
    handle.write(body)
    handle.close()
    return Path(handle.name)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OcrError as exc:
        print(exc)
        raise SystemExit(1)
