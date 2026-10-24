"""indexer：SQLite 索引 —— 表情元数据、MD5、pHash 的入库与增量更新。

数据库属于本工具自己的数据（默认放用户主目录 ~/.sticker-manager/），
与微信目录完全无关。
"""

from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .phash import phash_from_image
from .scanner import ScanResult, StickerFile

# 视觉可解析的格式（mp4 留 ffmpeg 钩子，MVP 阶段跳过哈希）
IMAGE_FORMATS = {"gif", "png", "jpg", "jpeg", "webp", "bmp"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stickers (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE,
  format TEXT,
  md5 TEXT,
  phash TEXT,
  size INTEGER,
  width INTEGER,
  height INTEGER,
  frames INTEGER,
  first_seen TEXT,
  mtime REAL,
  tags TEXT DEFAULT '',
  dat_key INTEGER
);
CREATE TABLE IF NOT EXISTS dup_groups (
  group_id INTEGER,
  sticker_id INTEGER UNIQUE,
  is_keeper INTEGER
);
CREATE INDEX IF NOT EXISTS idx_stickers_md5 ON stickers(md5);
CREATE INDEX IF NOT EXISTS idx_stickers_phash ON stickers(phash);
"""


def _ensure_column(conn: sqlite3.Connection, name: str, decl: str) -> None:
    """老库平滑迁移：缺列则补。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(stickers)")}
    if name not in cols:
        conn.execute(f"ALTER TABLE stickers ADD COLUMN {name} {decl}")


def default_db_path() -> Path:
    d = Path.home() / ".sticker-manager"
    d.mkdir(parents=True, exist_ok=True)
    return d / "stickers.db"


def md5_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def dat_xor_table(key: int) -> bytes:
    """单字节 XOR 的 translate 表（C 级速度解码整文件用）。"""
    return bytes(i ^ key for i in range(256))


def read_decoded(sf: StickerFile) -> bytes:
    """读源文件；dat 文件返回解码后的原始图片字节（只在内存中，不落盘）。"""
    with open(sf.path, "rb") as f:
        raw = f.read()
    if sf.dat_key is None:
        return raw
    return raw.translate(dat_xor_table(sf.dat_key))


def probe_file(sf: StickerFile) -> dict:
    """读取单个表情的完整元数据：md5 + 尺寸/帧数 + pHash（只读源文件）。

    dat 文件的 md5/pHash 都基于**解码后**内容计算：同一张图即使被
    用不同密钥存成两份 dat，也能正确判定为重复。
    """
    info = {"md5": None, "width": None, "height": None, "frames": None, "phash": None}
    try:
        data = read_decoded(sf)
    except OSError:
        data = None
    if data is not None:
        info["md5"] = hashlib.md5(data).hexdigest()
    if sf.format in IMAGE_FORMATS and data is not None:
        try:
            with Image.open(io.BytesIO(data)) as img:
                info["width"], info["height"] = img.size
                info["frames"] = getattr(img, "n_frames", 1)
                info["phash"] = phash_from_image(img)
        except Exception:
            pass  # 损坏文件：保留 md5，视觉字段留空
    return info


@dataclass
class IndexStats:
    scanned: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0   # size+mtime 未变，增量跳过
    errors: list = field(default_factory=list)


class StickerIndex:
    def __init__(self, db_path: str | os.PathLike | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        _ensure_column(self.conn, "dat_key", "INTEGER")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------- 入库

    def index_result(self, result: ScanResult, progress=None) -> IndexStats:
        """把一次扫描的结果入库（增量：同 path 且 size+mtime 未变则跳过）。"""
        stats = IndexStats(scanned=result.total)
        for i, sf in enumerate(result.files):
            try:
                action = self._upsert(sf)
                if action == "added":
                    stats.added += 1
                elif action == "updated":
                    stats.updated += 1
                else:
                    stats.skipped += 1
            except Exception as e:
                stats.errors.append(f"{sf.path}: {e}")
            if progress and (i % 50 == 0 or i == result.total - 1):
                progress(i + 1, result.total)
        self.conn.commit()
        return stats

    def _upsert(self, sf: StickerFile) -> str:
        """returns "added" | "updated" | "skipped"."""
        row = self.conn.execute(
            "SELECT id, size, mtime FROM stickers WHERE path = ?", (sf.path,)
        ).fetchone()
        if row and row["size"] == sf.size and row["mtime"] == sf.mtime:
            return "skipped"
        info = probe_file(sf)
        first_seen = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sf.mtime))
        if row:
            self.conn.execute(
                """UPDATE stickers SET format=?, md5=?, phash=?, size=?, width=?, height=?,
                   frames=?, first_seen=?, mtime=?, dat_key=? WHERE id=?""",
                (sf.format, info["md5"], info["phash"], sf.size, info["width"], info["height"],
                 info["frames"], first_seen, sf.mtime, sf.dat_key, row["id"]),
            )
            return "updated"
        self.conn.execute(
            """INSERT INTO stickers
               (path, format, md5, phash, size, width, height, frames, first_seen, mtime, dat_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sf.path, sf.format, info["md5"], info["phash"], sf.size, info["width"],
             info["height"], info["frames"], first_seen, sf.mtime, sf.dat_key),
        )
        return "added"

    # ------------------------------------------------------------- 查询

    def all_stickers(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM stickers ORDER BY first_seen DESC, id DESC")]

    def list_stickers(self, page: int = 1, per_page: int = 100, fmt: str | None = None,
                      tag: str | None = None, q: str | None = None) -> dict:
        """分页浏览；fmt/tag 过滤，q 对路径模糊匹配（预留搜索）。"""
        where, args = [], []
        if fmt:
            where.append("format = ?")
            args.append(fmt)
        if tag:
            where.append("(',' || tags || ',') LIKE ?")
            args.append(f"%,{tag},%")
        if q:
            where.append("path LIKE ?")
            args.append(f"%{q}%")
        cond = ("WHERE " + " AND ".join(where)) if where else ""
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM stickers {cond}", args).fetchone()[0]
        rows = self.conn.execute(
            f"""SELECT * FROM stickers {cond}
                ORDER BY first_seen DESC, id DESC LIMIT ? OFFSET ?""",
            args + [per_page, (page - 1) * per_page],
        ).fetchall()
        return {"total": total, "page": page, "per_page": per_page,
                "items": [dict(r) for r in rows]}

    def get(self, sticker_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM stickers WHERE id=?", (sticker_id,)).fetchone()
        return dict(r) if r else None

    def stats_summary(self) -> dict:
        rows = self.conn.execute(
            "SELECT format, COUNT(*) n FROM stickers GROUP BY format ORDER BY n DESC").fetchall()
        total = self.conn.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM stickers").fetchone()
        tagged = self.conn.execute(
            "SELECT COUNT(*) FROM stickers WHERE tags != ''").fetchone()[0]
        return {"total": total[0], "total_size": total[1], "by_format": {r["format"]: r["n"] for r in rows},
                "tagged": tagged}

    def set_tags(self, sticker_id: int, tags: list[str]) -> bool:
        cur = self.conn.execute(
            "UPDATE stickers SET tags=? WHERE id=?", (",".join(t.strip() for t in tags if t.strip()), sticker_id))
        self.conn.commit()
        return cur.rowcount > 0

    def all_tags(self) -> list[dict]:
        rows = self.conn.execute("SELECT tags FROM stickers WHERE tags != ''").fetchall()
        counter: dict[str, int] = {}
        for r in rows:
            for t in r["tags"].split(","):
                if t:
                    counter[t] = counter.get(t, 0) + 1
        return [{"tag": t, "count": n} for t, n in sorted(counter.items(), key=lambda kv: -kv[1])]
