"""A zero-dependency MCP server (stdio, newline-delimited JSON-RPC) that lets
Claude Code -- or any MCP client -- search and reason over your screen history.

This is the heart of Backscroll's "runs on your Claude Max subscription" idea:
the tool exposes your local capture database; the intelligence is whatever
model is driving the MCP client. No API keys, no cloud calls here.

Register with Claude Code:
    claude mcp add backscroll -- backscroll serve
"""

import json
import sys

from . import __version__, config, db
from .utils import fmt_ts, human_dur, parse_when

PROTOCOL_DEFAULT = "2025-06-18"

TOOLS = [
    {
        "name": "search_screen",
        "description": (
            "Full-text search across everything that has appeared on the user's "
            "screen (OCR text, app names, window titles). Use this to answer "
            "questions like 'what was that error I saw earlier', 'find the article "
            "about X I was reading', or 'what did that email from Dana say'. "
            "Returns matching moments with id, timestamp, app, window, and a text "
            "snippet. Call get_frame with an id for the full text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms (implicit AND), e.g. 'invoice stripe' or 'kubernetes crashloop'."},
                "limit": {"type": "integer", "description": "Max results (default 20).", "default": 20},
                "since": {"type": "string", "description": "Only results after this time. Relative ('2h','3d','1w') or ISO ('2026-07-23')."},
                "until": {"type": "string", "description": "Only results before this time."},
                "app": {"type": "string", "description": "Filter to an app name (substring), e.g. 'Chrome'."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_frame",
        "description": "Get the full OCR text and metadata for one captured frame by id (ids come from search_screen or get_timeline).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
    {
        "name": "get_timeline",
        "description": "List captured frames in a time range, newest first, to reconstruct what the user was doing. Returns app/window/timestamp per frame (not full text).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "Start of range, relative or ISO. Default '1h'."},
                "until": {"type": "string"},
                "limit": {"type": "integer", "default": 200},
            },
        },
    },
    {
        "name": "activity_summary",
        "description": "Summarize approximately how much time the user spent in each app over a time range (based on capture counts). Good for 'what did I work on today'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "Default 'today'."},
                "until": {"type": "string"},
            },
        },
    },
    {
        "name": "stats",
        "description": "Overall stats about the Backscroll database: frame count, date range, characters indexed.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _txt(obj):
    text = obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str)
    return {"content": [{"type": "text", "text": text}]}


def handle_call(name, args):
    con = db.connect()
    try:
        cfg = config.load()
        if name == "search_screen":
            rows = db.search(
                con,
                args.get("query", ""),
                limit=int(args.get("limit", 20) or 20),
                since_ts=parse_when(args.get("since")),
                until_ts=parse_when(args.get("until")),
                app=args.get("app"),
            )
            out = [
                {"id": r["id"], "time": fmt_ts(r["ts"]), "app": r["app"],
                 "window": r["window"], "snippet": r["snippet"]}
                for r in rows
            ]
            return _txt({"query": args.get("query", ""), "count": len(out), "results": out})

        if name == "get_frame":
            fr = db.get_frame(con, int(args["id"]))
            if not fr:
                return _txt(f"No frame with id {args.get('id')}")
            return _txt({
                "id": fr["id"], "time": fmt_ts(fr["ts"]), "app": fr["app"],
                "window": fr["window"], "image_path": fr["image_path"],
                "text": fr["ocr_text"],
            })

        if name == "get_timeline":
            rows = db.timeline(
                con,
                since_ts=parse_when(args.get("since") or "1h"),
                until_ts=parse_when(args.get("until")),
                limit=int(args.get("limit", 200) or 200),
            )
            out = [{"id": r["id"], "time": fmt_ts(r["ts"]), "app": r["app"], "window": r["window"]} for r in rows]
            return _txt({"count": len(out), "frames": out})

        if name == "activity_summary":
            since = parse_when(args.get("since") or "today")
            rows = db.app_summary(con, since_ts=since, until_ts=parse_when(args.get("until")), interval=cfg["interval"])
            out = [
                {"app": r["app"] or "(unknown)", "approx_time": human_dur(r["approx_seconds"]),
                 "frames": r["n"], "first": fmt_ts(r["first_ts"]), "last": fmt_ts(r["last_ts"])}
                for r in rows
            ]
            return _txt({"since": fmt_ts(since), "apps": out})

        if name == "stats":
            s = db.stats(con)
            return _txt({
                "frames": s["n"] or 0, "from": fmt_ts(s["first_ts"]),
                "to": fmt_ts(s["last_ts"]), "chars_indexed": s["chars"] or 0,
            })

        return _txt(f"Unknown tool: {name}")
    finally:
        con.close()


def serve():
    db.init_db()  # ensure schema exists even if the recorder never ran

    def send(obj):
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_DEFAULT),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "backscroll", "version": __version__},
            }})
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            try:
                result = handle_call(params.get("name"), params.get("arguments") or {})
                send({"jsonrpc": "2.0", "id": mid, "result": result})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}], "isError": True,
                }})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}})
