"""scanner 测试：magic bytes 嗅探、目录遍历过滤、微信目录探测、安全护栏。"""

from __future__ import annotations

import json
import os

from app.scanner import (
    detect_wechat_dirs,
    default_rules_path,
    is_probably_wechat_dir,
    scan_directory,
    sniff_format,
)

from .conftest import build_fake_wechat_home, make_image_file


def test_sniff_format_bytes():
    cases = {
        b"GIF89a.....": "gif",
        b"GIF87a.....": "gif",
        b"\x89PNG\r\n\x1a\n......": "png",
        b"\xff\xd8\xff\xe0.....": "jpg",
        b"RIFF\x00\x00\x00\x00WEBPVP8 ": "webp",
        b"\x00\x00\x00\x20ftypisom....": "mp4",
        b"BM\x00\x00\x00\x00...": "bmp",
        b"\x0a\x0b\x0c\x0d....": "unknown",
        b"": "unknown",
    }
    for head, fmt in cases.items():
        assert sniff_format(head) == fmt, head


def test_scan_directory_counts(sticker_factory):
    root, expected, _ = sticker_factory
    result = scan_directory(root)
    assert result.total == sum(expected.values())
    assert result.counts == expected
    assert not result.truncated


def test_scan_directory_max_files_truncates(sticker_factory):
    root, expected, _ = sticker_factory
    result = scan_directory(root, max_files=3)
    assert result.total == 3
    assert result.truncated


def test_scan_directory_small_file_skipped(sticker_factory):
    root, _, _ = sticker_factory
    result = scan_directory(root)
    names = [os.path.basename(f.path) for f in result.files]
    assert "tiny" not in names
    assert "th_a.gif" not in names


def build_fake_wechat_home(tmp_path):
    docs = tmp_path / "Documents"
    emo = docs / "WeChat Files" / "wxid_test123" / "FileStorage" / "CustomEmotion"
    emo.mkdir(parents=True)
    make_image_file(emo / "s1.gif", "gif")
    make_image_file(emo / "s2", "png")
    return tmp_path, emo


def test_detect_wechat_dirs_3x(tmp_path):
    home, emo = build_fake_wechat_home(tmp_path)
    found = detect_wechat_dirs(home=home)
    assert any(d.path == str(emo) and d.rule_id == "wechat3x" for d in found)
    d = next(d for d in found if d.path == str(emo))
    assert d.n_files == 2


def test_detect_wechat_dirs_none(tmp_path):
    empty = tmp_path / "nothing"  # 规则里没有任何匹配
    empty.mkdir()
    assert detect_wechat_dirs(home=empty) == []


def test_is_probably_wechat_dir(tmp_path):
    home, emo = build_fake_wechat_home(tmp_path)
    # 在探测目录内 → 拦
    assert is_probably_wechat_dir(emo / "x.gif")
    # 目录名含 WeChat Files 但未探测到（兜底判据）→ 拦
    assert is_probably_wechat_dir(r"D:\somewhere\WeChat Files\wxid_a\whatever")
    assert is_probably_wechat_dir(r"D:\somewhere\xwechat_files\wxid_a\msg")
    # 普通目录 / 上层公共目录 → 放行
    assert not is_probably_wechat_dir(tmp_path / "exports")
    assert not is_probably_wechat_dir(home / "Documents")


def test_default_rules_path_exists():
    p = default_rules_path()
    assert p.exists(), f"rules 文件缺失: {p}"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "roots" in data and len(data["roots"]) >= 2
