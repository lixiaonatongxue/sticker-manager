"""exporter 测试：扩展名补全、md5 命名去重、安全护栏（微信目录/源目录）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.exporter import ExportSafetyError, export_stickers
from app.indexer import StickerIndex
from app.scanner import scan_directory

from .conftest import build_fake_wechat_home, make_image_file


@pytest.fixture
def indexed(tmp_path):
    root = tmp_path / "CustomEmotion"
    root.mkdir()
    make_image_file(root / "a", "gif", size=64, hue=7)
    make_image_file(root / "b", "png", size=64, hue=8)
    make_image_file(root / "dupe1", "png", size=64, hue=9)
    make_image_file(root / "dupe2", "png", size=64, hue=9)  # 与 dupe1 同内容
    open(root / "x", "wb").write(b"\x0a\x0b\x0c\x0d" + b"\x7f" * 200)  # unknown
    idx = StickerIndex(tmp_path / "index.db")
    idx.index_result(scan_directory(root))
    return idx, root, tmp_path


def _ids(idx, *names):
    by_name = {Path(r["path"]).name: r["id"] for r in idx.all_stickers()}
    return [by_name[n] for n in names]


def test_export_adds_extension_and_copies(indexed):
    idx, root, tmp = indexed
    dest = tmp / "exports"
    r = export_stickers(idx, _ids(idx, "a", "b"), dest)
    assert r.summary() == {"exported": 2, "skipped": 0, "errors": 0}
    files = sorted(p.name for p in dest.iterdir())
    assert files == ["a.gif", "b.png"]
    # 字节一致
    assert (dest / "a.gif").read_bytes() == (root / "a").read_bytes()


def test_export_md5_naming_dedupes(indexed):
    idx, root, tmp = indexed
    dest = tmp / "exports"
    r = export_stickers(idx, _ids(idx, "dupe1", "dupe2"), dest, naming="md5")
    assert r.summary()["exported"] == 1
    assert len(list(dest.iterdir())) == 1
    assert r.skipped[0]["reason"] == "same_md5_already_exported"


def test_export_unknown_format_skipped(indexed):
    idx, root, tmp = indexed
    r = export_stickers(idx, _ids(idx, "x"), tmp / "exports")
    assert r.summary()["exported"] == 0
    assert r.skipped[0]["reason"] == "unknown_format"


def test_export_refuses_wechat_dir(indexed, tmp_path):
    idx, root, tmp = indexed
    home, emo = build_fake_wechat_home(tmp_path)
    with pytest.raises(ExportSafetyError):
        export_stickers(idx, _ids(idx, "a"), emo / "out")


def test_export_refuses_source_dir(indexed):
    idx, root, tmp = indexed
    with pytest.raises(ExportSafetyError):
        export_stickers(idx, _ids(idx, "a"), root / "sub")
    with pytest.raises(ExportSafetyError):
        export_stickers(idx, _ids(idx, "a"), root)


def test_export_collision_rename(indexed):
    idx, root, tmp = indexed
    dest = tmp / "exports"
    dest.mkdir()
    make_image_file(dest / "a.gif", "gif", size=32, hue=250)  # 占位同名文件，内容不同
    r = export_stickers(idx, _ids(idx, "a"), dest)
    assert r.summary()["exported"] == 1
    assert sorted(p.name for p in dest.iterdir()) == ["a-1.gif", "a.gif"]
