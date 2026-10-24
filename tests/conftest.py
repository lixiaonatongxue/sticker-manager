"""合成测试数据工厂：全部用程序生成的假表情文件，不含任何真实用户数据。"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw


def _gradient(size: int, channel: int = 0) -> Image.Image:
    """纯线性斜坡图（用于构造内容明显不同的图；对 pHash 是病理用例，勿用于近似判断）。"""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            v = (x * 255 // max(size - 1, 1), y * 255 // max(size - 1, 1), channel)
            px[x, y] = v
    return img


def _blob(size: int, hue: int = 0) -> Image.Image:
    """渐变背景 + 椭圆主体。hue 同时驱动配色和主体几何（位置/大小），
    因此不同 hue 是结构不同的图（pHash 距离 > 8），同 hue 不同 size 是
    同一张图的等比缩放（pHash 距离 ≤ 8）。
    """
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = (x * 200 // size, y * 200 // size, 90 + (hue % 160))
    draw = ImageDraw.Draw(img)
    r = size * (3 + hue % 3) // 10                 # 半径随 hue 变
    cx = size // 2 + ((hue % 5) - 2) * size // 16  # 圆心随 hue 漂移
    cy = size // 2 - ((hue % 3) - 1) * size // 16
    draw.ellipse([cx - r, cy - r * 3 // 4, cx + r, cy + r * 3 // 4], fill=(240, 90 + (hue % 160), 40))
    draw.ellipse([cx - r // 2, cy + r // 8, cx - r // 8, cy + r // 2], fill=(20, 30, 200))
    return img


def make_image_file(path, fmt: str, size: int = 64, hue: int = 0, kind: str = "blob") -> None:
    img = _blob(size, hue) if kind == "blob" else _gradient(size, hue)
    save_fmt = {"jpg": "JPEG", "gif": "GIF", "png": "PNG", "webp": "WEBP", "bmp": "BMP"}.get(fmt, fmt)
    img.save(path, format=save_fmt)


def make_fake_mp4(path, pad_to: int = 256) -> None:
    # 只有合法 mp4 文件头（供 magic bytes 测试），不是真视频
    path.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * (pad_to - 16))


def make_unknown_file(path, pad_to: int = 256) -> None:
    path.write_bytes(b"\x0a\x0b\x0c\x0d" + b"\x7f" * (pad_to - 4))


def build_fake_wechat_home(tmp_path):
    """构造一个假的微信 3.x 数据目录，返回 (home, CustomEmotion 目录)。"""
    docs = tmp_path / "Documents"
    emo = docs / "WeChat Files" / "wxid_test123" / "FileStorage" / "CustomEmotion"
    emo.mkdir(parents=True)
    make_image_file(emo / "s1.gif", "gif")
    make_image_file(emo / "s2", "png")
    return tmp_path, emo


@pytest.fixture
def sticker_factory(tmp_path):
    """在临时目录里批量造格式各异的表情文件，返回 (目录, 已知统计)。"""
    from app import scanner

    root = tmp_path / "CustomEmotion"
    root.mkdir()
    make_image_file(root / "a.gif", "gif")
    make_image_file(root / "b", "png")          # 微信文件无扩展名
    make_image_file(root / "c", "jpg", hue=100)
    make_image_file(root / "d", "webp", hue=200)
    make_fake_mp4(root / "e")
    make_unknown_file(root / "f")
    make_image_file(root / "th_a.gif", "gif")   # 缩略图，应跳过
    (root / "tiny").write_bytes(b"GIF89a")      # 过小，应跳过
    expected = {"gif": 1, "png": 1, "jpg": 1, "webp": 1, "mp4": 1, "unknown": 1}
    return root, expected, scanner
