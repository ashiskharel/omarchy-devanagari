"""What this computer is, and which engines that allows."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from devanagari.catalog import card_bytes, load_cards
from devanagari.errors import OcrError
from devanagari.gate import judge_download, judge_run
from devanagari.paths import probe_path
from devanagari.store import model_stored, support_url

_PROBE_CODE = """
import json
from pathlib import Path
path, = __import__("sys").argv[1:]
import onnxruntime
onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
available = 0
for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
    if line.startswith("MemAvailable:"):
        available = int(line.split()[1]) // 1024
        break
print(json.dumps({"freeMb": available}))
"""


def memory_mb() -> tuple[int, int]:
    total = available = 0
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, _, rest = line.partition(":")
        if key == "MemTotal":
            total = int(rest.split()[0]) // 1024
        elif key == "MemAvailable":
            available = int(rest.split()[0]) // 1024
    if total <= 0:
        raise OcrError("Could not read the memory on this machine.")
    return total, available


def cpu_name() -> str:
    name = ""
    threads = 0
    for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("model name") and not name:
            name = line.split(":", 1)[1].strip()
        elif line.startswith("processor"):
            threads += 1
    if not name:
        name = "unknown CPU"
    if threads:
        return f"{name} ({threads} threads)"
    return name


def gpu_name() -> str:
    try:
        result = subprocess.run(["lspci", "-nn"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "not reported"
    for line in result.stdout.splitlines():
        if "VGA" in line or "3D controller" in line or "Display controller" in line:
            label = line.split(": ", 1)[-1]
            named = re.search(r"\[([A-Za-z][^\]]+)\]", label)
            if named:
                return named.group(1).strip()
            return label.split(" [")[0].strip()
    return "not reported"


def tesseract_line() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "Tesseract is not installed."
    first = (result.stdout or result.stderr).splitlines()
    if result.returncode != 0 or not first:
        return False, "Tesseract is not installed."
    return True, first[0].strip()


def runtime_installed() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import onnxruntime"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def measure_load(model_path: Path) -> int | None:
    """Load the weights in a child process and return the RAM still free. None if it did not load."""
    if not model_path.is_file():
        return None
    cached = _cached_probe(model_path)
    if cached is not None:
        return cached
    try:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE_CODE, str(model_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        free = int(json.loads(result.stdout).get("freeMb"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    _store_probe(model_path, free)
    return free


def report(*, measure: bool = True) -> dict:
    total, available = memory_mb()
    binary_ok, binary = tesseract_line()
    runtime = runtime_installed()
    engines = []
    reader = ""
    for card in load_cards():
        engines.append(_engine(card, available, binary_ok, runtime, measure=measure))
    for engine in engines:
        if engine["id"] == "tesseract-nep" and engine["run"]:
            reader = engine["name"]
    if not binary_ok:
        line = "Tesseract is not installed, so this machine cannot read yet."
    elif reader:
        line = f"{available} MB free of {total} MB. Reading with {reader}."
    else:
        line = f"{available} MB free of {total} MB. Run devanagari fetch to install the Nepali data."
    optional = next((engine for engine in engines if engine["id"] == "ppocr-devanagari"), None)
    if optional and not optional["run"]:
        line += " " + _optional_clause(optional)
    return {
        "label": "अ",
        "line": line,
        "hardware": {
            "cpu": cpu_name(),
            "ramTotalMb": total,
            "ramAvailableMb": available,
            "gpu": gpu_name(),
            "tesseract": binary,
            "line": line,
        },
        "engines": engines,
        "last": _public_last(),
        "supportUrl": support_url(),
    }


def format_report(payload: dict) -> str:
    hardware = payload["hardware"]
    lines = [
        payload["line"],
        "",
        f"CPU     {hardware['cpu']}",
        f"Memory  {hardware['ramAvailableMb']} MB free of {hardware['ramTotalMb']} MB",
        f"GPU     {hardware['gpu']}",
        f"Reader  {hardware['tesseract']}",
        "",
        "Engines",
    ]
    for engine in payload["engines"]:
        lines.append(f"  {engine['name']}: {engine['detail']}")
    url = payload.get("supportUrl") or ""
    lines.append("")
    if url:
        lines.append(f"Free to use. Pay what you are comfortable with: {url}")
    else:
        lines.append("Free to use. Pay what you are comfortable with, including nothing.")
    return "\n".join(lines)


def _engine(card: dict, available: int, binary_ok: bool, runtime: bool, *, measure: bool) -> dict:
    stored = model_stored(card)
    allowed, why = judge_download(
        available,
        card_bytes(card),
        kind=card["kind"],
        published=bool(card["published"]),
        force=False,
    )
    if card["kind"] == "tessdata":
        if not binary_ok:
            detail = "Tesseract is not installed."
            action = "none"
            can_run = False
        elif stored:
            detail = "Installed. This is the reader."
            action = "none"
            can_run = True
        else:
            detail = f"Nepali data is not on this machine yet. {why}"
            action = "fetch" if allowed else "none"
            can_run = False
        return {
            "id": card["id"],
            "name": card["name"],
            "kind": card["kind"],
            "stored": stored,
            "download": action == "fetch",
            "run": can_run,
            "action": action,
            "detail": " ".join(detail.split()),
        }
    free_after = None
    if measure and stored and runtime:
        weights = next((item for item in card["files"] if str(item["name"]).endswith(".onnx")), None)
        if weights is not None:
            from devanagari.store import model_dir

            free_after = measure_load(model_dir(card["id"]) / weights["name"])
    can_run, run_why = judge_run(
        kind=card["kind"],
        stored=stored,
        runtime=runtime,
        free_after_load_mb=free_after,
    )
    if not card["published"]:
        detail = card["note"]
        action = "none"
        can_run = False
    elif stored:
        detail = f"Stored. {run_why} Page reading stays on Tesseract."
        action = "none"
    elif allowed:
        runtime_note = "ONNX runtime is not installed, and this plugin does not install it." if not runtime else run_why
        detail = f"{why} Download stores the weights. Reading stays on Tesseract: {runtime_note}"
        action = "download"
    else:
        detail = why
        action = "none"
        can_run = False
    return {
        "id": card["id"],
        "name": card["name"],
        "kind": card["kind"],
        "stored": stored,
        "download": allowed and not stored,
        "run": bool(can_run and card["kind"] == "tessdata"),
        "action": action,
        "detail": " ".join(detail.split()),
    }


def _optional_clause(engine: dict) -> str:
    if engine["stored"]:
        return "The optional model is stored and is not the reader."
    if engine["download"]:
        return "The optional Devanagari model can be downloaded and will not be loaded for reading."
    if engine["id"] == "ppocr-devanagari":
        return "The optional Devanagari model stays off."
    return ""


def _public_last() -> dict:
    from devanagari.store import load_last

    last = load_last()
    text = str(last.get("text") or "")
    if len(text) > 4000:
        text = text[:4000]
    return {
        "text": text,
        "engine": last.get("engine") or "",
        "source": last.get("source") or "",
        "error": last.get("error") or "",
    }


def _cached_probe(model_path: Path) -> int | None:
    path = probe_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if raw.get("path") != str(model_path) or raw.get("size") != model_path.stat().st_size:
        return None
    try:
        return int(raw["freeMb"])
    except (KeyError, TypeError, ValueError):
        return None


def _store_probe(model_path: Path, free_mb: int) -> None:
    from devanagari.paths import write_private

    payload = {"path": str(model_path), "size": model_path.stat().st_size, "freeMb": free_mb}
    write_private(probe_path(), json.dumps(payload) + "\n")
