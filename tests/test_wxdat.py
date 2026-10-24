"""wxdat 解码管线测试：嗅探密钥、解码哈希跨密钥去重、解码导出、解码缩略图。"""

from __future__ import annotations

import shutil

from app.exporter import export_stickers
from app.indexer import StickerIndex
from app.scanner import scan_directory, sniff_dat_key

from .conftest import make_image_file


def _make_dat(src_path, dst_path, key: int) -> None:
    """把明文图片文件转成微信风格单字节 XOR dat。"""
    data = src_path.read_bytes()
    dst_path.write_bytes(bytes(b ^ key for b in data))


def _indexed(tmp_path):
    root = tmp_path / "MsgAttach"
    root.mkdir()
    make_image_file(root / "meme1", "png", size=96, hue=42)      # 明文 png
    make_image_file(root / "meme2_src", "gif", size=64, hue=7)
    _make_dat(root / "meme2_src", root / "dat_a", 0xA5)           # 同一张图两种密钥
    _make_dat(root / "meme2_src", root / "dat_b", 0x33)
    (root / "meme2_src").unlink()
    make_image_file(root / "meme3_src", "jpg", size=80, hue=200)
    _make_dat(root / "meme3_src", root / "dat_c", 0x77)
    (root / "meme3_src").unlink()
    idx = StickerIndex(tmp_path / "wx.db")
    idx.index_result(scan_directory(root))
    return idx, root


def test_sniff_dat_key():
    assert sniff_dat_key(bytes(b ^ 0xA5 for b in b"GIF89a......")) == ("gif", 0xA5)
    assert sniff_dat_key(bytes(b ^ 0x33 for b in b"\x89PNG\r\n\x1a\n")) == ("png", 0x33)
    assert sniff_dat_key(bytes(b ^ 0x77 for b in b"\xff\xd8\xff\xe0")) == ("jpg", 0x77)
    assert sniff_dat_key(b"V1MMWX" + b"\x00" * 10) is None      # 真加密不动
    assert sniff_dat_key(b"\x0a\x0b\x0c\x0d\x0e") is None


def test_scan_detects_dat_format(tmp_path):
    idx, root = _indexed(tmp_path)
    try:
        by_name = {__import__("pathlib").Path(r["path"]).name: r for r in idx.all_stickers()}
        assert by_name["dat_a"]["format"] == "gif" and by_name["dat_a"]["dat_key"] == 0xA5
        assert by_name["dat_b"]["format"] == "gif" and by_name["dat_b"]["dat_key"] == 0x33
        assert by_name["meme1"]["format"] == "png" and by_name["meme1"]["dat_key"] is None
    finally:
        idx.close()


def test_cross_key_dedup(tmp_path):
    """同图不同密钥的两份 dat：md5 相同、pHash 相同 → 精确重复组。"""
    idx, root = _indexed(tmp_path)
    try:
        from app.deduper import compute_duplicates
        report = compute_duplicates(idx)
        g = next(g for g in report.groups
                 if {__import__("pathlib").Path(m["path"]).name for m in g.members} == {"dat_a", "dat_b"})
        assert g.kind == "exact" and len(g.members) == 2
        # 解码后元数据完整
        m = next(m for m in g.members if __import__("pathlib").Path(m["path"]).name == "dat_a")
        assert m["width"] == 64 and m["frames"] == 1 and m["phash"]
    finally:
        idx.close()


def test_export_decodes_dat(tmp_path):
    idx, root = _indexed(tmp_path)
    try:
        by_name = {__import__("pathlib").Path(r["path"]).name: r for r in idx.all_stickers()}
        dest = tmp_path / "exports"
        r = export_stickers(idx, [by_name["dat_a"]["id"], by_name["dat_c"]["id"], by_name["meme1"]["id"]], dest)
        assert r.summary()["exported"] == 3
        assert sorted(p.name for p in dest.iterdir()) == ["dat_a.gif", "dat_c.jpg", "meme1.png"]
        # 导出的是可打开的标准图片（PIL 能读 = 真解开了）
        from PIL import Image
        with Image.open(dest / "dat_a.gif") as img:
            assert img.size == (64, 64)
        with Image.open(dest / "dat_c.jpg") as img:
            assert img.size == (80, 80)
    finally:
        idx.close()


def test_thumbnail_decodes_dat(client, tmp_path):
    from app.server import app
    c, root, tmp = client
    from app.scanner import scan_directory
    from app.indexer import StickerIndex
    d = tmp / "dats"
    d.mkdir()
    make_image_file(d / "s", "png", size=64, hue=11)
    _make_dat(d / "s", d / "t", 0x5A)
    (d / "s").unlink()
    idx = StickerIndex(tmp / "thumb.db")
    idx.index_result(scan_directory(d))
    idx.close()
    old = app.state.db_path
    app.state.db_path = tmp / "thumb.db"
    try:
        r = c.get("/api/thumbnail/1")
        assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
        from PIL import Image
        import io
        with Image.open(io.BytesIO(r.content)) as img:
            assert img.size[0] <= 320
    finally:
        app.state.db_path = old
