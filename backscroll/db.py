"""SQLite storage + FTS5 full-text search for captured frames."""

import re
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
  id         INTEGER PRIMARY KEY,
  ts         INTEGER NOT NULL,
  app        TEXT,
  window     TEXT,
  display    INTEGER,
  image_path TEXT,
  ocr_text   TEXT,
  text_len   INTEGER,
  phash      TEXT
);
CREATE INDEX IF NOT EXISTS idx_frames_ts  ON frames(ts);
CREATE INDEX IF NOT EXISTS idx_frames_app ON frames(app);

CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
  ocr_text, app, window,
  content='frames', content_rowid='id',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS frames_ai AFTER INSERT ON frames BEGIN
  INSERT INTO frames_fts(rowid, ocr_text, app, window)
  VALUES (new.id, new.ocr_text, new.app, new.window);
END;
CREATE TRIGGER IF NOT EXISTS frames_ad AFTER DELETE ON frames BEGIN
  INSERT INTO frames_fts(frames_fts, rowid, ocr_text, app, window)
  VALUES ('delete', old.id, old.ocr_text, old.app, old.window);
END;
"""


def connect():
    config.ensure_dirs()
    con = sqlite3.connect(str(config.DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    return con


def insert_frame(con, ts, app, window, display, image_path, ocr_text, phash):
    text = ocr_text or ""
    cur = con.execute(
        "INSERT INTO frames(ts, app, window, display, image_path, ocr_text, text_len, phash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, app, window, display, image_path, text, len(text), phash),
    )
    con.commit()
    return cur.lastrowid


def _fts_query(q):
    """Build a safe FTS5 MATCH expression: quote each whitespace-delimited
    term (giving an implicit AND) so arbitrary user input never breaks the
    FTS5 query grammar."""
    terms = [t for t in re.split(r"\s+", (q or "").strip()) if t]
    return " ".join('"' + t.replace('"', '""') + '"' for t in terms)


def search(con, query, limit=20, since_ts=None, until_ts=None, app=None):
    fts = _fts_query(query)
    if not fts:
        return []
    where = ["frames_fts MATCH ?"]
    params = [fts]
    if since_ts:
        where.append("f.ts >= ?")
        params.append(since_ts)
    if until_ts:
        where.append("f.ts <= ?")
        params.append(until_ts)
    if app:
        where.append("f.app LIKE ?")
        params.append(f"%{app}%")
    sql = f"""
      SELECT f.id, f.ts, f.app, f.window, f.image_path, f.text_len,
             snippet(frames_fts, 0, '[', ']', ' ... ', 12) AS snippet,
             bm25(frames_fts) AS score
      FROM frames_fts
      JOIN frames f ON f.id = frames_fts.rowid
      WHERE {' AND '.join(where)}
      ORDER BY score
      LIMIT ?
    """
    params.append(limit)
    return [dict(r) for r in con.execute(sql, params)]


def get_frame(con, frame_id):
    r = con.execute("SELECT * FROM frames WHERE id = ?", (frame_id,)).fetchone()
    return dict(r) if r else None


def timeline(con, since_ts=None, until_ts=None, limit=200):
    where, params = [], []
    if since_ts:
        where.append("ts >= ?")
        params.append(since_ts)
    if until_ts:
        where.append("ts <= ?")
        params.append(until_ts)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT id, ts, app, window, text_len, image_path FROM frames {w} ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in con.execute(sql, params)]


def app_summary(con, since_ts=None, until_ts=None, interval=15):
    where, params = [], []
    if since_ts:
        where.append("ts >= ?")
        params.append(since_ts)
    if until_ts:
        where.append("ts <= ?")
        params.append(until_ts)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT app, COUNT(*) n, MIN(ts) first_ts, MAX(ts) last_ts FROM frames {w} GROUP BY app ORDER BY n DESC"
    rows = []
    for r in con.execute(sql, params):
        d = dict(r)
        d["approx_seconds"] = d["n"] * interval
        rows.append(d)
    return rows


def stats(con):
    r = con.execute(
        "SELECT COUNT(*) n, MIN(ts) first_ts, MAX(ts) last_ts, SUM(text_len) chars FROM frames"
    ).fetchone()
    return dict(r)


def prune(con, before_ts):
    rows = con.execute("SELECT image_path FROM frames WHERE ts < ?", (before_ts,)).fetchall()
    for r in rows:
        p = r["image_path"]
        if p:
            try:
                (config.FRAMES_DIR / p).unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass
    cur = con.execute("DELETE FROM frames WHERE ts < ?", (before_ts,))
    con.commit()
    con.execute("INSERT INTO frames_fts(frames_fts) VALUES('optimize')")
    con.commit()
    return cur.rowcount
