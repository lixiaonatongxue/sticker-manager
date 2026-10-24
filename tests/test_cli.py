"""CLI 测试：scan → report → export 全链路（合成数据）。"""

from __future__ import annotations

import shutil

from app.cli import main

from .conftest import make_image_file


def _prepare(tmp_path):
    root = tmp_path / "CustomEmotion"
    root.mkdir()
    make_image_file(root / "a", "gif", size=64, hue=7)
    make_image_file(root / "a_copy", "gif", size=64, hue=7)
    make_image_file(root / "b", "png", size=96, hue=200)
    make_image_file(root / "b_small", "png", size=48, hue=200)
    return root


def test_scan_report_export_flow(tmp_path, capsys):
    root = _prepare(tmp_path)
    db = tmp_path / "cli.db"

    assert main(["--db", str(db), "scan", "--path", str(root)]) == 0
    out = capsys.readouterr().out
    assert "入库: 新增 4" in out

    assert main(["--db", str(db), "report"]) == 0
    out = capsys.readouterr().out
    assert "已索引 4 个表情" in out
    assert "重复组 2 个" in out          # a/a_copy 一组，b/b_small 一组
    assert "可精简文件 2 个" in out

    dest = tmp_path / "exports"
    assert main(["--db", str(db), "export", "--dest", str(dest), "--keepers"]) == 0
    out = capsys.readouterr().out
    assert "成功 2" in out
    files = sorted(p.name for p in dest.iterdir())
    assert files == ["a.gif", "b.png"]   # b 取 96px keeper

    # 二次扫描增量：全部 skipped
    assert main(["--db", str(db), "scan", "--path", str(root)]) == 0
    out = capsys.readouterr().out
    assert "未变 4" in out


def test_scan_max_files_cap(tmp_path, capsys):
    root = _prepare(tmp_path)
    assert main(["--db", str(tmp_path / "c.db"), "scan", "--path", str(root), "--max-files", "2"]) == 0
    out = capsys.readouterr().out
    assert "受限抽样扫描" in out


def test_export_refusal_exit_code(tmp_path, capsys):
    root = _prepare(tmp_path)
    db = tmp_path / "cli.db"
    main(["--db", str(db), "scan", "--path", str(root)])
    capsys.readouterr()
    rc = main(["--db", str(db), "export", "--dest", str(root / "sub"), "--ids", "1"])
    assert rc == 2
    assert "已拒绝导出" in capsys.readouterr().out


def test_report_empty_db(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "empty.db"), "report"]) == 1
    assert "索引为空" in capsys.readouterr().out
