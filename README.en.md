# Sticker Manager 表情包管家

[简体中文](README.md) | English

> A fully local WeChat sticker manager: auto-locate sticker files, sniff real formats, visual deduplication, tag filtering, and one-click batch export.


![demo](docs/demo.gif)

## Why

WeChat ships zero sticker management: hundreds of saved stickers with no search, no bulk export, duplicates piling up across group chats, everything lost when you reinstall — and no way to take your collection to Telegram/QQ.

## Features (v0.1)

| Feature | Notes |
|---|---|
| Auto-locate | Detects WeChat 3.x / 4.x sticker dirs (including user-chosen data drives); manual folder fallback |
| Format sniffing | WeChat files have no extension — real format (gif/png/jpg/webp/bmp/mp4) detected via magic bytes |
| Exact dedup | Full MD5 clustering in seconds |
| Visual dedup | In-house pHash (pure-numpy DCT, no scipy) clusters the same sticker across compressions/sizes |
| Grid UI | Thumbnail waterfall, format/tag/path filters, select & export with correct extensions |
| Backup mode | Export everything, including encrypted `unknown` files, verbatim as `.dat` |
| CLI | `detect` / `scan` / `report` / `export` / `serve` |

See the [roadmap](#roadmap) for what's next.

## Compliance — the four no's

1. **Never injects or attaches** to the WeChat process
2. **No WeChat private protocol, no network** (web UI binds 127.0.0.1 only)
3. **Read-only** on your own files; **never writes into WeChat dirs** (exports into WeChat dirs are hard-refused)
4. Export destination is always user-chosen; the tool offers **no delete capability** at all

The codebase is fully auditable. The index database (`~/.sticker-manager/stickers.db`) stores metadata and hashes only.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/lixiaonatongxue/sticker-manager.git
cd sticker-manager
pip install -e ".[dev]"        # installs the sticker-manager command

# optional: build the web UI (CLI works without it)
cd web && npm install && npm run build && cd ..
```

## Usage

### Web UI (recommended)

```bash
sticker-manager serve
# open http://127.0.0.1:8765
```

Click "Scan (incremental)" → review the "Duplicates" tab → select & export.

### CLI

```bash
sticker-manager detect                                    # detect wechat sticker dirs
sticker-manager scan                                      # index (incremental; --path to pick any folder)
sticker-manager report                                    # dedup report with keeper marks
sticker-manager export --dest D:\my-stickers --keepers     # export best of each dup group
sticker-manager export --dest D:\backup --all --include-unknown   # full backup, encrypted files as .dat
```

> It's really a "folder sticker deduper" — not tied to WeChat paths. Telegram export folders and QQ sticker folders work just as well.

## Important: WeChat encryption status & decoding capability (field-tested)

Verified on a real machine (2026-10, WeChat 3.x + 4.x side by side):

- **Emoticon stores proper**: 4.x `business\emoticon` and recent 3.x `CustomEmotion` (`V1MMWX` header) use strong encryption (not XOR; known-plaintext attacks fail). Keys live in WeChat process memory — **reading process memory violates this tool's compliance line (no injection/attachment), so we don't**. Those files are classified `unknown` and can be backed up verbatim as `.dat`; format research is welcome.
- **Chat image stores ARE decodable**: 3.x `FileStorage\MsgAttach`, `Image`, and `Fav` hold large numbers of memes sent as image messages, stored as classic **single-byte-XOR dat** (public community knowledge for years). This tool ships an **offline decode pipeline**: sniff the key → decode in memory → MD5/pHash computed on decoded content (identical memes under different keys still dedupe) → thumbnails and exports are standard GIF/PNG/JPG.
- **If your WeChat version stores plain files, everything works out of the box.**

## Architecture

```
sticker-manager/
├── app/
│   ├── scanner.py    # dir detection (rules + wechat config mining) + magic-byte sniffing
│   ├── phash.py      # perceptual hash (pure numpy DCT-II)
│   ├── indexer.py    # sqlite index: metadata, md5, phash; incremental upserts
│   ├── deduper.py    # exact dedup -> union-find phash clustering -> keeper marking
│   ├── exporter.py   # batch export with wechat-dir/source-dir safety rails
│   └── server.py     # fastapi local api (127.0.0.1 only)
├── web/              # vue3 + vite frontend
├── rules/paths.json  # wechat dir detection rules (community-updatable)
├── scripts/          # e.g. make_demo.py - synthetic demo dataset generator
└── tests/            # 37 unit/integration tests (synthetic data only)
```

## Development

```bash
pip install -e ".[dev]"
pytest                        # run tests
python scripts/make_demo.py   # regenerate the demo dataset
cd web && npm run dev         # frontend dev mode (proxies to :8765)
```

## Roadmap

- [x] v0.2: click-to-tag UI; backup mode (.dat verbatim export for encrypted files)
- [ ] v0.3: local CLIP (ONNX) auto-tagging in Chinese, fully offline
- [ ] v1.0: watchdog incremental indexing, i18n, PyInstaller single-file build
- [ ] community: research on the V1MMWX / 4.x encrypted formats

## License

MIT
