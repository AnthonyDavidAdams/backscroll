"""Small shared helpers: time parsing and formatting."""

import re
import time
from datetime import datetime

_REL = re.compile(r"^-?(\d+)\s*([smhdw])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def now_ts():
    return int(time.time())


def parse_when(s, now=None):
    """Parse a time expression into a unix timestamp (seconds).

    Accepts:
      - relative: '30m', '2h', '3d', '1w', '-90m'  (interpreted as "ago")
      - 'now', 'today', 'yesterday'
      - ISO 8601: '2026-07-23', '2026-07-23T14:00'
      - a raw unix int/float or 9+ digit numeric string
    Returns None if s is falsy or unparseable.
    """
    if s is None or s == "":
        return None
    now = now if now is not None else time.time()
    if isinstance(s, (int, float)):
        return int(s)
    s = str(s).strip()
    low = s.lower()
    if low == "now":
        return int(now)
    if low == "today":
        d = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        return int(d.timestamp())
    if low == "yesterday":
        d = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        return int(d.timestamp()) - 86400
    m = _REL.match(low)
    if m:
        secs = int(m.group(1)) * _UNITS[m.group(2)]
        return int(now - secs)
    if re.fullmatch(r"\d{9,}", s):
        return int(s)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return int(dt.timestamp())
    except Exception:
        return None


def fmt_ts(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(int(ts)).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def human_dur(seconds):
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"
