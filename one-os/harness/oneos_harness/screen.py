"""Screen assertions: QMP screendump + optional OCR (tesseract)."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .qemu import VM


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _prepare(png: Path) -> Path:
    """Boot menus draw light text on busy backgrounds, which tesseract reads poorly.

    Grayscale, upscale ×2, keep only bright pixels (the text) and render them dark on
    white. Returns the original path if Pillow isn't installed.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return png
    img = ImageOps.grayscale(Image.open(png))
    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
    img = img.point(lambda v: 0 if v > 200 else 255)
    out = png.with_suffix(".ocr.png")
    img.save(out)
    return out


def ocr(png: Path) -> str:
    if not ocr_available():
        raise RuntimeError("tesseract not installed")
    text = ""
    # Raw first (works for plain consoles), then the preprocessed image.
    for candidate in (png, _prepare(png)):
        out = subprocess.run(["tesseract", str(candidate), "-", "--psm", "11"],
                             capture_output=True, text=True, check=False)
        text += out.stdout + "\n"
    return text


def wait_text(vm: VM, needle: str, timeout: float, every: float = 3.0) -> str:
    """Poll screendumps until OCR finds `needle` (case-insensitive). Returns the OCR text."""
    deadline = time.monotonic() + vm.cfg.t(timeout)
    last, i = "", 0
    while time.monotonic() < deadline:
        if not vm.alive():
            break
        png = vm.screendump(vm.dir / f"{vm.name}.screen.{i:03d}.png")
        i += 1
        last = ocr(png)
        if needle.lower() in last.lower():
            return last
        time.sleep(every)
    raise AssertionError(f"{needle!r} not on screen within {vm.cfg.t(timeout):.0f}s; last OCR:\n{last}")
