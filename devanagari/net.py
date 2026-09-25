"""HTTPS downloads with a byte cap and a checksum. The body is never executed."""

from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
from pathlib import Path

from devanagari.errors import OcrError


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not str(newurl).startswith("https://"):
            raise OcrError("The download redirected off https.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str, dest: Path, sha256: str, cap: int, timeout: int = 90) -> None:
    """Save url to dest. Refuse a body larger than cap, then check sha256."""
    if not url.startswith("https://"):
        raise OcrError("Downloads use https only.")
    dest.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    opener = urllib.request.build_opener(_HttpsOnly)
    request = urllib.request.Request(url, headers={"User-Agent": "omarchy-devanagari"})
    try:
        with opener.open(request, timeout=timeout) as response:
            declared = response.headers.get("Content-Length")
            if declared:
                try:
                    size = int(declared)
                except ValueError:
                    size = None
                else:
                    if size > cap:
                        raise OcrError(f"The file says it is {size} bytes, over the {cap} byte cap.")
            digest = hashlib.sha256()
            got = 0
            with partial.open("wb") as handle:
                while True:
                    block = response.read(64 * 1024)
                    if not block:
                        break
                    got += len(block)
                    if got > cap:
                        raise OcrError(f"The download passed the {cap} byte cap.")
                    digest.update(block)
                    handle.write(block)
    except OcrError:
        partial.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise OcrError(f"Could not download the file: {exc}") from exc
    if digest.hexdigest() != sha256:
        partial.unlink(missing_ok=True)
        raise OcrError("The download did not match the pinned checksum.")
    os.replace(partial, dest)
