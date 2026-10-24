from __future__ import annotations

import hashlib
import os

from app.indexer import StickerIndex
from app.scanner import scan_directory

from .conftest import make_image_file


def _index(tmp_path, root):
    idx = StickerIndex(tmp_path / "index.db")
    result = scan_directory(root)
    stats = idx.index_result(result)
    return idx, stats, result


def test_index_and_metadata(sticker_factory, tmp_path):
    root, expected, _ = sticker_factory
    idx, stats, result = _index(tmp_path, root)
    try:
        assert stats.added == sum(expected.values())
        assert stats.errors == []
        summary = idx.stats_summary()
        assert summary["total"] == sum(expected.values())
        # 元数据完整：图片有尺寸和 phash，mp4/unknown 有 md5 无 phash
        gif = next(r for r in idx.all_stickers() if r["format"] == "gif")
        assert gif["width"] == 64 and gif["height"] == 64
        assert gif["frames"] == 1 and len(gif["phash"]) == 16
        mp4 = next(r for r in idx.all_stickers() if r["format"] == "mp4")
        assert mp4["phash"] is None and mp4["md5"]
        # md5 与独立计算一致
        assert gif["md5"] == hashlib.md5(open(gif["path"], "rb").read()).hexdigest()
    finally:
        idx.close()


def test_incremental_skip(sticker_factory, tmp_path):
    root, expected, _ = sticker_factory
    idx, s1, _ = _index(tmp_path, root)
    _, s2, _ = _index(tmp_path, root)
    try:
        assert s1.added == sum(expected.values())
        assert s2.skipped == sum(expected.values()) and s2.added == 0
        assert idx.stats_summary()["total"] == sum(expected.values())
    finally:
        idx.close()


def test_file_change_updates(sticker_factory, tmp_path):
    root, _, _ = sticker_factory
    idx, s1, _ = _index(tmp_path, root)
    target = next(f for f in idx.all_stickers() if f["format"] == "png")
    old_md5 = target["md5"]
    make_image_file(target["path"], "png", size=96, hue=123)  # 改内容
    os.utime(target["path"], None)
    _, s2, _ = _index(tmp_path, root)
    try:
        assert s2.updated >= 1
        new = idx.get(target["id"])
        assert new["md5"] != old_md5 and new["width"] == 96
    finally:
        idx.close()


def test_pagination_and_tag(sticker_factory, tmp_path):
    root, _, _ = sticker_factory
    idx, _, _ = _index(tmp_path, root)
    try:
        page = idx.list_stickers(page=1, per_page=2)
        assert page["total"] == 6 and len(page["items"]) == 2
        page2 = idx.list_stickers(page=3, per_page=2)
        assert len(page2["items"]) == 2  # 6 = 2+2+2
        page3 = idx.list_stickers(page=4, per_page=2)
        assert page3["items"] == []
        only_gif = idx.list_stickers(fmt="gif")
        assert only_gif["total"] == 1 and only_gif["items"][0]["format"] == "gif"
        # 标签
        first_id = page["items"][0]["id"]
        assert idx.set_tags(first_id, ["开心", " 猫 ", ""])
        assert idx.get(first_id)["tags"] == "开心,猫"
        assert idx.all_tags() == [{"tag": "开心", "count": 1}, {"tag": "猫", "count": 1}]
        assert idx.list_stickers(tag="开心")["total"] == 1
    finally:
        idx.close()
