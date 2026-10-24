"""pHash 测试：同图同哈希、缩放近似、镜像远离、坏文件返回 None。"""

from __future__ import annotations

from PIL import Image

from app.phash import hamming_hex, phash_file, phash_from_image

from .conftest import _blob, make_fake_mp4, make_image_file


def test_hash_format():
    h = phash_from_image(_blob(64, 1))
    assert len(h) == 16  # 64 bit -> 16 hex
    int(h, 16)


def test_identical_images_same_hash(tmp_path):
    make_image_file(tmp_path / "a.png", "png", size=64, hue=50)
    make_image_file(tmp_path / "b.png", "png", size=64, hue=50)
    assert phash_file(str(tmp_path / "a.png")) == phash_file(str(tmp_path / "b.png"))


def test_resized_variant_is_near(tmp_path):
    make_image_file(tmp_path / "big.png", "png", size=128, hue=50)
    make_image_file(tmp_path / "small.png", "png", size=48, hue=50)
    d = hamming_hex(phash_file(str(tmp_path / "big.png")), phash_file(str(tmp_path / "small.png")))
    assert d <= 8, f"缩放后距离过大: {d}"


def test_mirrored_image_is_far(tmp_path):
    img = _blob(64, 30)
    img.save(tmp_path / "orig.png", format="PNG")
    img.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(tmp_path / "mirror.png", format="PNG")
    d = hamming_hex(phash_file(str(tmp_path / "orig.png")), phash_file(str(tmp_path / "mirror.png")))
    assert d > 8, f"镜像后距离过小: {d}"


def test_unreadable_returns_none(tmp_path):
    make_fake_mp4(tmp_path / "v.mp4")
    assert phash_file(str(tmp_path / "v.mp4")) is None
    assert phash_file(str(tmp_path / "missing.png")) is None
    assert hamming_hex(phash_file(str(tmp_path / "v.mp4")), "0" * 16) == 64


def test_gif_first_frame(tmp_path):
    make_image_file(tmp_path / "a.gif", "gif", size=64, hue=77)
    h = phash_file(str(tmp_path / "a.gif"))
    assert h is not None and len(h) == 16
