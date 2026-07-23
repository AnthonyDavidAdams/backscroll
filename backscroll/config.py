"""Paths and user configuration for Backscroll.

All state lives under ~/.backscroll (override with $BACKSCROLL_HOME):
  backscroll.db       SQLite database (frames + FTS index)
  frames/YYYY-MM-DD/  compressed JPEG frames (optional)
  config.json         user settings
  bsocr               compiled OCR helper (cached per machine)
  recorder.pid        running recorder's pid
"""

import json
import os
from pathlib import Path

HOME = Path.home()
DATA_DIR = Path(os.environ.get("BACKSCROLL_HOME", HOME / ".backscroll"))
DB_PATH = DATA_DIR / "backscroll.db"
FRAMES_DIR = DATA_DIR / "frames"
PID_PATH = DATA_DIR / "recorder.pid"
CONFIG_PATH = DATA_DIR / "config.json"
OCR_BIN = DATA_DIR / "bsocr"

DEFAULTS = {
    "interval": 15,          # seconds between captures
    "store_images": True,    # keep compressed JPEG frames on disk
    "jpeg_max_width": 1600,  # downscale longest side to this many px
    "jpeg_quality": 40,      # JPEG quality 0-100
    "retention_days": 30,    # prune frames older than this (0 = keep forever)
    "min_text_len": 0,       # skip frames whose OCR text is shorter than this
    "display": 1,            # display index to capture (1 = main)
}


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)


def load():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except Exception:
            pass
    return cfg


def save(cfg):
    ensure_dirs()
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
