"""Screen capture, frame hashing, active-window detection, and JPEG
compression -- all via macOS built-in tools (screencapture, sips, osascript),
so there are no third-party dependencies."""

import hashlib
import subprocess
from pathlib import Path


def capture_display(tmp_png, display=1):
    """Capture a display to a PNG. Requires Screen Recording permission.
    Returns True on success."""
    cmd = ["screencapture", "-x", "-t", "png"]
    if display and display > 0:
        cmd += ["-D", str(display)]
    cmd.append(str(tmp_png))
    proc = subprocess.run(cmd, capture_output=True)
    p = Path(tmp_png)
    return proc.returncode == 0 and p.exists() and p.stat().st_size > 0


def file_hash(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def active_window():
    """Return (app_name, window_title). Empty strings if unavailable, e.g.
    when Accessibility permission has not been granted."""
    script = (
        'tell application "System Events"\n'
        " set p to first application process whose frontmost is true\n"
        " set appName to name of p\n"
        ' set winName to ""\n'
        " try\n"
        "  set winName to name of front window of p\n"
        " end try\n"
        ' return appName & "\\n" & winName\n'
        "end tell"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=5
        )
    except Exception:
        return "", ""
    if proc.returncode != 0:
        return "", ""
    parts = proc.stdout.rstrip("\n").split("\n", 1)
    app = parts[0] if parts else ""
    win = parts[1] if len(parts) > 1 else ""
    return app, win


def compress_jpeg(src_png, dst_jpg, max_width=1600, quality=40):
    """Downscale + JPEG-compress a PNG using sips. Returns True on success."""
    cmd = [
        "sips", "-Z", str(max_width),
        "-s", "format", "jpeg",
        "-s", "formatOptions", str(quality),
        str(src_png), "--out", str(dst_jpg),
    ]
    proc = subprocess.run(cmd, capture_output=True)
    return proc.returncode == 0 and Path(dst_jpg).exists()
