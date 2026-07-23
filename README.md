# Backscroll

**A local, searchable memory of everything on your screen — and the AI that
queries it is your own Claude subscription.**

Backscroll is an open-source, zero-dependency, macOS-first alternative to
[Screenpipe](https://screenpipe.com) / Rewind. It quietly captures your
screen on an interval, runs on-device OCR, and stores the text in a local
SQLite database with full-text search. Then it exposes that history as an
**MCP server** — so Claude Code (or any MCP client) can answer questions like
*"what was that error I saw an hour ago?"* or *"find the invoice number from
that Stripe page"* without you paying for a separate model.

The whole point: **no bundled LLM, no API keys, no cloud.** The intelligence
is whatever model is already driving your MCP client. If you have Claude Code
Max, you already have everything you need to reason over your own screen
history — Backscroll just hands it the data.

```
your screen  ->  screencapture  ->  Vision OCR  ->  SQLite + FTS5
                                                          |
                                                    MCP server
                                                          |
                                              Claude Code / any MCP client
```

## Why it's different

- **Zero Python dependencies.** Pure standard library plus one tiny Swift
  helper (compiled on first run). No pip install of a 400 MB ML stack.
- **On-device OCR** via Apple's Vision framework — free, offline, fast.
- **Your model, your bill.** The MCP server contains no model calls. Point it
  at Claude Code, Claude Desktop, or anything that speaks MCP.
- **Everything stays local.** Frames and text never leave your machine. The
  database is a plain SQLite file you can inspect, back up, or delete.
- **Honest about privacy.** Recording your screen is powerful and sensitive.
  Backscroll makes it a deliberate, inspectable, easily-revoked choice.

## Requirements

- macOS (uses `screencapture`, `sips`, `osascript`, and the Vision framework)
- Python 3.9+
- Xcode command-line tools (`xcode-select --install`) — needed once to compile
  the OCR helper

## Install

```bash
git clone https://github.com/AnthonyDavidAdams/backscroll.git
cd backscroll
pip install -e .          # installs the `backscroll` command
```

Or run it without installing, straight from the repo:

```bash
python3 -m backscroll <command>
```

### Grant permissions

Recording the screen requires macOS permissions. Grant them to the app that
runs Backscroll (your terminal, or the Python binary if you use the launch
agent):

- **Screen Recording** — System Settings > Privacy & Security > Screen
  Recording. Without this, captured frames are blank wallpaper.
- **Accessibility** — System Settings > Privacy & Security > Accessibility.
  Optional; enables front-window titles.

Then verify:

```bash
backscroll doctor
```

## Use it

```bash
# start recording (foreground; Ctrl+C to stop)
backscroll start

# ...or record 24/7 in the background via a macOS launch agent
backscroll install-agent
backscroll uninstall-agent     # stop it

# search from the terminal
backscroll search "stripe invoice"
backscroll search "kubernetes crashloop" --since 3d --app Terminal

# what were you doing?
backscroll timeline --since 2h
backscroll stats
backscroll status
```

## Connect it to Claude Code

Register Backscroll's MCP server so Claude can query your screen history:

```bash
claude mcp add backscroll -- backscroll serve
```

(If you didn't `pip install`, use the module form and set the repo on the path:
`claude mcp add backscroll -- python3 -m backscroll serve`.)

Now ask Claude things like:

- "Search my screen history for the invoice number I saw on Stripe today."
- "What error was in my terminal about an hour ago?"
- "Summarize what apps I spent time in this morning."
- "Find the article about interpretability I was reading yesterday and give me
  the key points."

Claude calls the `search_screen`, `get_frame`, `get_timeline`,
`activity_summary`, and `stats` tools under the hood.

Works with any MCP client (Claude Desktop, etc.) — the server speaks standard
newline-delimited JSON-RPC over stdio.

## Configuration

Settings live in `~/.backscroll/config.json`. View or change them:

```bash
backscroll config                          # print current config
backscroll config interval=10 store_images=false
```

| key             | default | meaning                                             |
| --------------- | ------- | --------------------------------------------------- |
| `interval`      | 15      | seconds between captures                            |
| `store_images`  | true    | keep compressed JPEG frames on disk (or text only)  |
| `jpeg_max_width`| 1600    | downscale frames to this longest edge               |
| `jpeg_quality`  | 40      | JPEG quality (0–100)                                 |
| `retention_days`| 30      | prune frames older than this (0 = keep forever)     |
| `min_text_len`  | 0       | skip frames with less OCR text than this            |
| `display`       | 1       | display index to capture (1 = main)                 |

Identical consecutive frames (an idle screen) are detected by hash and skipped,
so a still screen costs almost nothing. Trim old data anytime:

```bash
backscroll prune --days 14
```

## Where things live

Everything is under `~/.backscroll` (override with `$BACKSCROLL_HOME`):

```
~/.backscroll/
  backscroll.db          SQLite database (frames + FTS index)
  frames/YYYY-MM-DD/     compressed JPEG frames (if store_images)
  config.json            your settings
  bsocr                  compiled OCR helper (per machine)
  recorder.pid           the running recorder
```

To wipe your history: stop the recorder and `rm -rf ~/.backscroll`.

## Privacy and consent

Backscroll records your screen. Treat it accordingly.

- All data is local and unencrypted on disk. Anything visible on screen —
  passwords in plaintext, private messages, financial data — can be captured
  and OCR'd. Use `retention_days`, `prune`, and `store_images=false` to limit
  exposure, and consider full-disk encryption (FileVault).
- Only record your own device, and be mindful of others' content (shared
  screens, video calls, other people's messages).
- Nothing is uploaded by Backscroll itself. When you ask Claude a question, the
  relevant snippets are sent to your MCP client's model as part of that
  request — same as any other prompt you send it.

## How it compares to Screenpipe

Screenpipe is a capable, cross-platform, Rust-based product with continuous
video, audio transcription, and a plugin marketplace. Backscroll is
deliberately smaller: macOS-only, screen-text-only (for now), no bundled
models, no daemon you don't control — a few hundred lines you can read in one
sitting, built to plug straight into a Claude Code subscription.

## Roadmap

- Audio capture + transcription (whisper.cpp) as an optional module
- Multi-display and per-app capture rules (allow/deny lists)
- Optional at-rest encryption for the database and frames
- Perceptual-hash dedupe and smarter idle detection
- Linux/Windows capture + OCR backends

## Contributing

Issues and PRs welcome. Keep it dependency-light and local-first.

## License

MIT © EarthPilot
