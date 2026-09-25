"""Plain checks for the machine-check rules and the PDF text path."""

from __future__ import annotations

import tempfile
from pathlib import Path

from devanagari.errors import OcrError
from devanagari.gate import judge_download, judge_run, optional_need_mb
from devanagari.ocr import read_path
from devanagari.score import character_error


def main() -> int:
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
    assert character_error("नेपाल", "नेपाल") == 0
    assert character_error("नेपाल", "नेपा") < 0.3

    pdf = _text_pdf("Hello Nepal this page already has a text layer.")
    record = read_path(pdf, source="check")
    assert "Hello Nepal" in record["text"]
    print("checks ok")
    return 0


def _text_pdf(words: str) -> Path:
    stream = f"BT /F1 12 Tf 20 50 Td ({words}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
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
