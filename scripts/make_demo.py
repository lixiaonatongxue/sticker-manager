"""生成演示用表情数据（纯合成文字梗风格图片，非真实用户数据）。

用法：python scripts/make_demo.py --out data/demo
生成 CustomEmotion/ 目录（含精确重复、近似重复、unknown 假加密文件），
供演示 / GIF 录制 / 手动体验用。测试套件不依赖此脚本。
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXTS = [
    "哈哈哈", "收到", "OK", "摸鱼中", "裂开", "yyds", "666", "awsl",
    "Emo了", "卷不动了", "躺平", "真香", "打工人", "芭比Q了", "社恐",
    "摆烂", "上岸!", "冲!", "晚安", "在吗", "栓Q", "笑不活了", "哦？", "稳",
]
PALETTES = [
    ((255, 94, 98), (255, 195, 113)),   # 珊瑚橙
    ((56, 189, 248), (129, 140, 248)),  # 天蓝紫
    ((52, 211, 153), (59, 130, 246)),   # 青绿蓝
    ((251, 191, 36), (245, 101, 101)),  # 金红
    ((167, 139, 250), (236, 72, 153)),  # 紫粉
    ((34, 197, 94), (132, 204, 22)),    # 绿
]
FONTS = [
    "C:/Windows/Fonts/msyhbd.ttc",  # 微软雅黑 Bold
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",  # 黑体
]


def make_meme(size: int, text: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    c1, c2 = PALETTES[rng.randrange(len(PALETTES))]
    img = Image.new("RGB", (size, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        for x in range(0, size):
            img.putpixel((x, y), (r, g, b))
    # 装饰圆点：全部用相对坐标（rng.random() 每次恰好消耗一个随机数，
    # 保证同 seed 不同尺寸时圆点位置等比一致，pHash 才能跨缩放聚类）
    draw = ImageDraw.Draw(img)
    for _ in range(4):
        r = size * (0.06 + 0.12 * rng.random())
        x, y = rng.random() * size, rng.random() * size
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    # 主文字（占比大才稳：pHash 对占画面 40% 的粗文字跨缩放距离 ≤6）
    font = None
    for fp in FONTS:
        try:
            font = ImageFont.truetype(fp, int(size * 0.40))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    boxed = draw.textbbox((0, 0), text, font=font)
    tw, th = boxed[2] - boxed[0], boxed[3] - boxed[1]
    tx, ty = (size - tw) // 2, (size - th) // 2
    # 阴影 + 描边效果
    draw.text((tx + 5, ty + 5), text, font=font, fill=(0, 0, 0, 90))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255),
              stroke_width=max(2, size // 70), stroke_fill=(30, 30, 30))
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/demo", help="输出根目录")
    ap.add_argument("--n", type=int, default=26, help="生成文字梗数量")
    args = ap.parse_args()

    root = Path(args.out) / "CustomEmotion"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    texts = (TEXTS * 3)[: args.n]
    i = 0
    for i, text in enumerate(texts):
        size = random.Random(i * 7).choice([220, 240, 260, 280, 300])
        make_meme(size, text, i).save(root / f"m{i:03d}", format="PNG")

    # 精确重复（同参数重新生成 = 字节级相同，再复制一份）
    size0 = random.Random(0).choice([220, 240, 260, 280, 300])
    make_meme(size0, texts[0], 0).save(root / "m000", format="PNG")
    make_meme(size0, texts[0], 0).save(root / "dup_of_m000", format="PNG")
    # 近似重复：同文字不同尺寸/种子
    make_meme(180, texts[1], 1).save(root / "near_m001_small", format="PNG")
    make_meme(300, texts[1], 1).save(root / "near_m001_big", format="PNG")
    # 假 mp4 + 假加密 dat（演示 unknown 备份）
    (root / "fake_mp4").write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 300)
    (root / "fake_dat").write_bytes(b"V1MMWX" + bytes(range(250)))

    n = len(list(root.iterdir()))
    print(f"生成完成: {root}（{n} 个文件）")


if __name__ == "__main__":
    main()
