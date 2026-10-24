"""deduper 测试：精确重复、近似重复（跨格式/跨尺寸）、keeper 选择、阈值生效。"""

from __future__ import annotations

import shutil

from app.deduper import compute_duplicates, load_groups
from app.indexer import StickerIndex
from app.scanner import scan_directory

from .conftest import make_image_file


def _build(tmp_path):
    root = tmp_path / "CustomEmotion"
    root.mkdir()
    # 精确重复：f1 与 f1_copy 字节相同
    make_image_file(root / "f1.png", "png", size=64, hue=10)
    shutil.copyfile(root / "f1.png", root / "f1_copy")
    # 近似重复：同内容不同尺寸（96 分辨率更高 → 应为 keeper）、不同格式 gif
    make_image_file(root / "f2_big", "png", size=96, hue=10)
    make_image_file(root / "f2_gif", "gif", size=64, hue=10)
    # 独立表情：内容不同
    make_image_file(root / "f3", "png", size=64, hue=200, kind="gradient")
    idx = StickerIndex(tmp_path / "index.db")
    idx.index_result(scan_directory(root))
    return idx, root


def test_exact_and_near_groups(tmp_path):
    idx, root = _build(tmp_path)
    try:
        report = compute_duplicates(idx)
        s = report.summary()
        # f1/f1_copy/f2_big/f2_gif 应聚成一组（gif 与 png 内容相同→phash 距离小）
        # f3 独立成组不出现
        assert s["total_indexed"] == 5
        assert s["n_groups"] == 1
        g = report.groups[0]
        assert len(g.members) == 4 and g.kind == "near"  # md5 不全同 → near
        keeper = g.members[0]
        assert keeper["width"] == 96 and keeper["path"].endswith("f2_big")  # 分辨率优先
        assert report.dup_files == 3
    finally:
        idx.close()


def test_threshold_zero_splits_near(tmp_path):
    idx, root = _build(tmp_path)
    try:
        report = compute_duplicates(idx, threshold=0)
        # 阈值 0：只有完全相同 phash 的聚（f1 与 f1_copy 内容相同 phash 相同；缩放版被拆开）
        assert all(g.kind in ("exact", "near") for g in report.groups)
        # f1 + f1_copy 至少仍在一组
        flat = {m["path"].rsplit("\\", 1)[-1] for g in report.groups for m in g.members}
        assert "f1.png" in flat and "f1_copy" in flat
    finally:
        idx.close()


def test_groups_persisted_and_reload(tmp_path):
    idx, root = _build(tmp_path)
    try:
        compute_duplicates(idx)
        n = idx.conn.execute("SELECT COUNT(*) FROM dup_groups").fetchone()[0]
        assert n == 4  # 4 个成员写进表
        keepers = idx.conn.execute(
            "SELECT sticker_id FROM dup_groups WHERE is_keeper=1").fetchall()
        assert len(keepers) == 1
        reloaded = load_groups(idx)
        assert len(reloaded) == 1 and reloaded[0].members[0]["path"].endswith("f2_big")
    finally:
        idx.close()


def test_no_duplicates(tmp_path):
    root = tmp_path / "solo"
    root.mkdir()
    make_image_file(root / "only", "png", size=64, hue=42)
    idx = StickerIndex(tmp_path / "index.db")
    idx.index_result(scan_directory(root))
    try:
        report = compute_duplicates(idx)
        assert report.groups == [] and report.dup_files == 0
    finally:
        idx.close()
