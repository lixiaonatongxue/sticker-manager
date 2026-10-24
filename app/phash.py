"""pHash 感知哈希：纯 numpy + Pillow 实现，算法与经典 imagehash.phash 一致。

用正交 DCT-II 基矩阵手写变换，避免引入 scipy 依赖（安装体积大、打包臃肿）。
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

HASH_SIZE = 8          # 8x8 = 64 bit
IMG_SIZE = HASH_SIZE * 4  # 32x32，与 imagehash 相同的缩放尺寸


@lru_cache(maxsize=4)
def _dct_basis(n: int) -> np.ndarray:
    """构造 n×n 正交 DCT-II 基矩阵：B @ A == B.T（A 为 n×n 图像块）。"""
    k = np.arange(n).reshape(-1, 1)
    i = np.arange(n).reshape(1, -1)
    b = np.cos(np.pi * (2 * i + 1) * k / (2 * n)) * np.sqrt(2.0 / n)
    b[0, :] = np.sqrt(1.0 / n)
    return b


def phash_from_image(img: Image.Image, hash_size: int = HASH_SIZE) -> str:
    """对 PIL Image（取到的即首帧）计算感知哈希，返回 16 位 hex 字符串。"""
    img_size = hash_size * 4
    gray = img.convert("L").resize((img_size, img_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float64)
    b = _dct_basis(img_size)
    dct = b @ pixels @ b.T
    low = dct[:hash_size, :hash_size]
    med = np.median(low)
    bits = (low > med).flatten()
    return _pack_bits(bits)


def phash_file(path: str) -> str | None:
    """读取图片文件首帧算 pHash；打不开（如 mp4、加密 dat）返回 None。"""
    try:
        with Image.open(path) as img:
            return phash_from_image(img)
    except Exception:
        return None


def hamming_hex(a: str, b: str) -> int:
    """两个 hex 哈希的汉明距离；长度不一致返回 64（视为完全不相似）。"""
    if not a or not b or len(a) != len(b):
        return HASH_SIZE * HASH_SIZE
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _pack_bits(bits: np.ndarray) -> str:
    v = 0
    for bit in bits:
        v = (v << 1) | int(bit)
    return f"{v:0{len(bits) // 4}x}"
