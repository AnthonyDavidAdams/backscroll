"""On-device OCR via a compiled Swift/Vision helper.

The helper is compiled from ocr_helper/BSOCR.swift on first use and cached at
~/.backscroll/bsocr, so there is no manual build step and no Python image
dependency -- macOS Vision does all the work, offline.
"""

import subprocess
from pathlib import Path

from . import config

HELPER_SRC = Path(__file__).parent / "ocr_helper" / "BSOCR.swift"


def ensure_helper():
    """Compile the Swift OCR helper if needed; return the binary path."""
    binp = config.OCR_BIN
    if binp.exists() and binp.stat().st_size > 0:
        return binp
    config.ensure_dirs()
    if not HELPER_SRC.exists():
        raise FileNotFoundError(f"OCR helper source missing: {HELPER_SRC}")
    proc = subprocess.run(
        ["swiftc", "-O", "-o", str(binp), str(HELPER_SRC)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to compile OCR helper (need Xcode CLT):\n{proc.stderr}")
    return binp


def ocr_image(path):
    """Return recognized text for an image, or '' on failure."""
    binp = ensure_helper()
    try:
        proc = subprocess.run(
            [str(binp), str(path)], capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()
