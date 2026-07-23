"""The capture loop: grab a frame, dedupe against the last one, OCR it,
store the text (and optionally a compressed image), repeat."""

import os
import signal
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from . import capture, config, db, ocr

_running = True


def _stop(signum, frame):
    global _running
    _running = False


def write_pid():
    config.ensure_dirs()
    config.PID_PATH.write_text(f"{os.getpid()}\n{int(time.time())}\n")


def clear_pid():
    try:
        config.PID_PATH.unlink()
    except FileNotFoundError:
        pass


def is_running():
    """Return the recorder pid if one is alive, else None."""
    if not config.PID_PATH.exists():
        return None
    try:
        pid = int(config.PID_PATH.read_text().split()[0])
    except Exception:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        return None


def run(interval=None, store_images=None, display=None, verbose=True):
    global _running
    _running = True
    cfg = config.load()
    interval = interval or cfg["interval"]
    if store_images is None:
        store_images = cfg["store_images"]
    if display is None:
        display = cfg.get("display", 1)
    max_w = cfg["jpeg_max_width"]
    quality = cfg["jpeg_quality"]
    min_len = cfg.get("min_text_len", 0)

    con = db.init_db()
    ocr.ensure_helper()  # compile up front so failures surface immediately
    write_pid()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    last_hash = None
    n = 0
    if verbose:
        print(f"backscroll: recording every {interval}s -> {config.DB_PATH}")
        print("If frames look empty, grant Screen Recording (and Accessibility "
              "for window titles) in System Settings > Privacy & Security.")
        print("Press Ctrl+C to stop.")

    try:
        while _running:
            t0 = time.time()
            tmp = None
            try:
                fd, tmp_name = tempfile.mkstemp(suffix=".png", prefix="bs_")
                os.close(fd)
                tmp = Path(tmp_name)
                if not capture.capture_display(tmp, display):
                    raise RuntimeError("screencapture failed (Screen Recording permission?)")
                h = capture.file_hash(tmp)
                if h != last_hash:
                    last_hash = h
                    text = ocr.ocr_image(tmp)
                    if len(text) >= min_len:
                        app, win = capture.active_window()
                        image_rel = None
                        if store_images:
                            day = datetime.now().strftime("%Y-%m-%d")
                            outdir = config.FRAMES_DIR / day
                            outdir.mkdir(parents=True, exist_ok=True)
                            fname = f"{int(t0)}_{display}.jpg"
                            if capture.compress_jpeg(tmp, outdir / fname, max_w, quality):
                                image_rel = f"{day}/{fname}"
                        db.insert_frame(con, int(t0), app, win, display, image_rel, text, h)
                        n += 1
                        if verbose and n % 20 == 0:
                            print(f"  {n} frames captured (last: {app} - {win[:40]})")
            except Exception as e:
                if verbose:
                    print(f"[warn] {e}", file=sys.stderr)
            finally:
                if tmp:
                    try:
                        tmp.unlink()
                    except Exception:
                        pass
            # keep cadence while staying responsive to stop signals
            end = t0 + interval
            while _running and time.time() < end:
                time.sleep(min(0.5, max(0.0, end - time.time())))
    finally:
        clear_pid()
        con.close()
        if verbose:
            print(f"\nStopped. {n} new frames this session.")
