"""Backscroll command-line interface."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__, capture, config, db, ocr, recorder
from .utils import fmt_ts, human_dur, now_ts, parse_when


def cmd_start(a):
    running = recorder.is_running()
    if running:
        print(f"Already recording (pid {running}).")
        return 1
    recorder.run(
        interval=a.interval,
        store_images=(False if a.no_images else None),
        display=a.display,
    )
    return 0


def cmd_status(a):
    pid = recorder.is_running()
    con = db.init_db()
    s = db.stats(con)
    con.close()
    print(f"Recorder: {'RUNNING (pid %d)' % pid if pid else 'stopped'}")
    print(f"Frames:   {s['n'] or 0}")
    if s["last_ts"]:
        print(f"Last:     {fmt_ts(s['last_ts'])} ({human_dur(now_ts() - s['last_ts'])} ago)")
    print(f"Database: {config.DB_PATH}")
    return 0


def cmd_search(a):
    con = db.init_db()
    rows = db.search(
        con, a.query, limit=a.limit,
        since_ts=parse_when(a.since), until_ts=parse_when(a.until), app=a.app,
    )
    con.close()
    if not rows:
        print("No matches.")
        return 0
    for r in rows:
        print(f"[{r['id']}] {fmt_ts(r['ts'])}  {r['app'] or ''} - {(r['window'] or '')[:50]}")
        print(f"    {r['snippet']}")
    return 0


def cmd_timeline(a):
    con = db.init_db()
    rows = db.timeline(con, since_ts=parse_when(a.since or "1h"), until_ts=parse_when(a.until), limit=a.limit)
    con.close()
    for r in rows:
        print(f"[{r['id']}] {fmt_ts(r['ts'])}  {r['app'] or ''} - {(r['window'] or '')[:60]}")
    return 0


def cmd_stats(a):
    con = db.init_db()
    s = db.stats(con)
    apps = db.app_summary(con, since_ts=parse_when("today"), interval=config.load()["interval"])
    con.close()
    print(f"Frames: {s['n'] or 0}")
    print(f"Range:  {fmt_ts(s['first_ts'])} -> {fmt_ts(s['last_ts'])}")
    print(f"Chars:  {s['chars'] or 0:,}")
    if apps:
        print("\nToday by app:")
        for r in apps[:15]:
            print(f"  {human_dur(r['approx_seconds']):>8}  {r['app'] or '(unknown)'}")
    return 0


def cmd_prune(a):
    cfg = config.load()
    days = a.days if a.days is not None else cfg["retention_days"]
    if not days:
        print("Retention is 0 (keep forever); nothing pruned.")
        return 0
    con = db.init_db()
    n = db.prune(con, now_ts() - days * 86400)
    con.close()
    print(f"Pruned {n} frames older than {days} days.")
    return 0


def cmd_serve(a):
    from . import mcp_server
    mcp_server.serve()
    return 0


def cmd_config(a):
    cfg = config.load()
    for kv in (a.set or []):
        k, _, v = kv.partition("=")
        k, v = k.strip(), v.strip()
        if k not in config.DEFAULTS:
            print(f"Unknown key: {k}")
            continue
        default = config.DEFAULTS[k]
        if isinstance(default, bool):
            cfg[k] = v.lower() in ("1", "true", "yes", "on")
        elif isinstance(default, int):
            cfg[k] = int(v)
        else:
            cfg[k] = v
    if a.set:
        config.save(cfg)
    print(json.dumps(cfg, indent=2))
    return 0


def cmd_doctor(a):
    ok = True
    print("Backscroll doctor")
    print("-----------------")

    # Xcode command-line tools + OCR helper
    try:
        binp = ocr.ensure_helper()
        print(f"[ok]   OCR helper compiled: {binp}")
    except Exception as e:
        ok = False
        print(f"[FAIL] OCR helper: {e}")
        print("       Install Xcode command-line tools: xcode-select --install")

    # Screen Recording permission -> capture + OCR a real frame
    fd, tmp_name = tempfile.mkstemp(suffix=".png", prefix="bs_doctor_")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if capture.capture_display(tmp, config.load().get("display", 1)):
            text = ocr.ocr_image(tmp) if tmp.exists() else ""
            if len(text.strip()) >= 5:
                print(f"[ok]   Screen capture + OCR working ({len(text)} chars from a live frame).")
            else:
                ok = False
                print("[warn] Captured a frame but OCR text was nearly empty.")
                print("       Grant Screen Recording to your terminal in")
                print("       System Settings > Privacy & Security > Screen Recording, then retry.")
        else:
            ok = False
            print("[FAIL] screencapture failed. Grant Screen Recording permission and retry.")
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

    # Accessibility permission -> window titles
    app, win = capture.active_window()
    if app:
        print(f"[ok]   Active-window detection working (front app: {app}).")
    else:
        print("[warn] Could not read the active window. For window titles, grant")
        print("       Accessibility in System Settings > Privacy & Security > Accessibility.")

    con = db.init_db()
    s = db.stats(con)
    con.close()
    print(f"[info] Database: {config.DB_PATH} ({s['n'] or 0} frames)")
    print("\nAll good." if ok else "\nSome checks need attention (see above).")
    return 0 if ok else 1


PLIST_LABEL = "com.earthpilot.backscroll"


def cmd_install_agent(a):
    repo_root = str(Path(__file__).resolve().parent.parent)
    out_log = str(config.DATA_DIR / "recorder.out.log")
    err_log = str(config.DATA_DIR / "recorder.err.log")
    config.ensure_dirs()
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>-m</string>
    <string>backscroll</string>
    <string>start</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key><string>{repo_root}</string>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin</string>
  </dict>
  <key>WorkingDirectory</key><string>{repo_root}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{out_log}</string>
  <key>StandardErrorPath</key><string>{err_log}</string>
</dict>
</plist>
"""
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist)
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    print(f"Wrote {plist_path}")
    if r.returncode == 0:
        print("Loaded. Backscroll will now record at login and stay running.")
        print("Stop it with:  backscroll uninstall-agent")
    else:
        print(f"launchctl load returned an error:\n{r.stderr}")
        print("Note: grant Screen Recording permission to the Python binary above if frames are empty.")
    return 0


def cmd_uninstall_agent(a):
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    try:
        plist_path.unlink()
        print(f"Removed {plist_path} and stopped the background recorder.")
    except FileNotFoundError:
        print("No launch agent installed.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="backscroll",
        description="A local, searchable memory of your screen. Queryable by Claude via MCP.",
    )
    p.add_argument("-V", "--version", action="version", version=f"backscroll {__version__}")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("start", help="Start recording the screen (foreground).")
    s.add_argument("--interval", type=int, default=None, help="Seconds between captures.")
    s.add_argument("--display", type=int, default=None, help="Display index (1 = main).")
    s.add_argument("--no-images", action="store_true", help="Store OCR text only; keep no screenshots.")
    s.set_defaults(func=cmd_start)

    sub.add_parser("status", help="Show recorder status and DB summary.").set_defaults(func=cmd_status)

    s = sub.add_parser("search", help="Full-text search your screen history.")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--since", default=None, help="e.g. 2h, 3d, 2026-07-23")
    s.add_argument("--until", default=None)
    s.add_argument("--app", default=None)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("timeline", help="List recent frames (what you were doing).")
    s.add_argument("--since", default="1h")
    s.add_argument("--until", default=None)
    s.add_argument("--limit", type=int, default=200)
    s.set_defaults(func=cmd_timeline)

    sub.add_parser("stats", help="Show capture stats and today's app breakdown.").set_defaults(func=cmd_stats)

    s = sub.add_parser("prune", help="Delete frames older than the retention window.")
    s.add_argument("--days", type=int, default=None)
    s.set_defaults(func=cmd_prune)

    sub.add_parser("serve", help="Run the MCP server over stdio (for Claude Code).").set_defaults(func=cmd_serve)

    s = sub.add_parser("config", help="Show or set configuration (key=value).")
    s.add_argument("set", nargs="*", help="e.g. interval=10 store_images=false")
    s.set_defaults(func=cmd_config)

    sub.add_parser("doctor", help="Check permissions and toolchain.").set_defaults(func=cmd_doctor)
    sub.add_parser("install-agent", help="Record 24/7 via a macOS launch agent.").set_defaults(func=cmd_install_agent)
    sub.add_parser("uninstall-agent", help="Stop and remove the launch agent.").set_defaults(func=cmd_uninstall_agent)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    return args.func(args)
