"""CLI 入口：探测 / 扫描 / 去重报告 / 导出。

用法：
  sticker-manager detect                          # 自动探测微信表情目录
  sticker-manager scan [--path 目录] [--max-files N] [--db 路径]
  sticker-manager report [--threshold 8] [--db 路径]
  sticker-manager export --dest 目录 [--ids 1,2,3 | --keepers] [--naming md5] [--db 路径]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .deduper import DEFAULT_THRESHOLD, compute_duplicates, load_groups
from .exporter import ExportSafetyError, export_stickers
from .indexer import StickerIndex
from .scanner import detect_wechat_dirs, scan_multiple


def cmd_detect(args) -> int:
    found = detect_wechat_dirs()
    if not found:
        print("未自动探测到微信表情目录。请用 scan --path 手动指定文件夹。")
        return 1
    print("探测到以下微信表情目录：")
    for d in found:
        print(f"  [{d.label}] {d.path}  （{d.n_files} 个文件）")
    return 0


def _open_index(args) -> StickerIndex:
    return StickerIndex(Path(args.db) if args.db else None)


def cmd_scan(args) -> int:
    if args.path:
        roots = [args.path]
    else:
        found = detect_wechat_dirs()
        if not found:
            print("未探测到微信表情目录，请用 --path 手动指定。")
            return 1
        roots = [d.path for d in found]
        print(f"自动探测到 {len(roots)} 个微信表情目录，全部扫描：")
        for d in found:
            print(f"  [{d.label}] {d.path}（{d.n_files} 个文件）")

    print(f"扫描中: 共 {len(roots)} 个目录" + (f"（限 {args.max_files} 个文件）" if args.max_files else ""))
    result = scan_multiple(roots, max_files=args.max_files)
    idx = _open_index(args)
    try:
        stats = idx.index_result(result, progress=lambda i, n: _progress(i, n))
        print()
        fmt_line = "  ".join(f"{k}:{v}" for k, v in sorted(result.counts.items()))
        print(f"文件 {result.total} 个（{fmt_line}）")
        if result.truncated:
            print("注意：达到 --max-files 限额，本次为受限抽样扫描。")
        print(f"入库: 新增 {stats.added}，更新 {stats.updated}，未变 {stats.skipped}，出错 {len(stats.errors)}")
        for e in stats.errors[:5]:
            print(f"  ! {e}")
    finally:
        idx.close()
    return 0


def _progress(done: int, total: int) -> None:
    pct = done * 100 // max(total, 1)
    sys.stdout.write(f"\r索引进度 {done}/{total} ({pct}%)")
    sys.stdout.flush()


def cmd_report(args) -> int:
    idx = _open_index(args)
    try:
        summary = idx.stats_summary()
        if summary["total"] == 0:
            print("索引为空，请先执行 scan。")
            return 1
        print(f"已索引 {summary['total']} 个表情，格式分布: {summary['by_format']}")
        print(f"计算重复组（阈值 {args.threshold}）...")
        report = compute_duplicates(idx, threshold=args.threshold)
        s = report.summary()
        print("=" * 60)
        print(f"重复组 {s['n_groups']} 个（精确 {s['n_exact']}，近似 {s['n_near']}），"
              f"可精简文件 {s['dup_files']} 个")
        print("=" * 60)
        for g in report.groups[: args.top]:
            size_kb = g.members[0]["size"] / 1024
            print(f"\n[组 {g.group_id}] {g.kind} × {len(g.members)}  keeper={Path(g.members[0]['path']).name} ({size_kb:.0f} KB)")
            for m in g.members:
                tag = "★keeper" if m["id"] == g.keeper_id else "       "
                w = f"{m['width']}x{m['height']}" if m["width"] else "?"
                print(f"  {tag}  id={m['id']:<5} {w:<10} {Path(m['path']).name}")
        if len(report.groups) > args.top:
            print(f"\n... 其余 {len(report.groups) - args.top} 组略（--top 调整显示数量）")
        print("\n提示：本工具不删除任何文件；用 export --keepers 导出每组最优版本。")
    finally:
        idx.close()
    return 0


def cmd_export(args) -> int:
    idx = _open_index(args)
    try:
        if args.all:
            ids = [r["id"] for r in idx.all_stickers()]
            if not ids:
                print("索引为空，请先执行 scan。")
                return 1
        elif args.ids:
            ids = [int(x) for x in args.ids.split(",") if x.strip()]
        elif args.keepers:
            ids = [g.keeper_id for g in load_groups(idx)]
            if not ids:
                print("没有重复组。可先运行 report，或用 --ids 指定导出对象。")
                return 1
        else:
            print("请指定 --ids / --keepers / --all 之一")
            return 1
        try:
            r = export_stickers(idx, ids, args.dest, naming=args.naming,
                                include_unknown=args.include_unknown)
        except ExportSafetyError as e:
            print(f"已拒绝导出：{e}")
            return 2
        s = r.summary()
        print(f"导出完成: 成功 {s['exported']}，跳过 {s['skipped']}，失败 {s['errors']} → {args.dest}")
        for sk in r.skipped[:10]:
            print(f"  跳过 id={sk['id']} 原因={sk['reason']}")
        for err in r.errors[:10]:
            print(f"  ! {err}")
        return 0 if r.ok else 1
    finally:
        idx.close()


def cmd_serve(args) -> int:
    from .server import main as serve_main
    serve_main(port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sticker-manager", description="表情包管家：本地微信表情去重/导出（只读、不联网）")
    p.add_argument("--db", help="索引数据库路径（默认 ~/.sticker-manager/stickers.db）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("detect", help="自动探测微信表情目录")

    sp = sub.add_parser("scan", help="扫描目录并建立索引")
    sp.add_argument("--path", help="表情目录（默认自动探测）")
    sp.add_argument("--max-files", type=int, default=None,
                    help="最多收录文件数（受限抽样测试用）")

    rp = sub.add_parser("report", help="生成去重报告")
    rp.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="pHash 汉明距离阈值，默认 8")
    rp.add_argument("--top", type=int, default=20, help="最多显示的重复组数")

    ep = sub.add_parser("export", help="导出选中表情")
    ep.add_argument("--dest", required=True, help="导出目的地（微信目录/源目录会被拒绝）")
    ep.add_argument("--ids", help="逗号分隔的 id 列表")
    ep.add_argument("--keepers", action="store_true", help="导出每个重复组的 keeper（精选）")
    ep.add_argument("--all", action="store_true", help="备份模式：导出索引内全部表情")
    ep.add_argument("--include-unknown", action="store_true",
                    help="unknown/加密文件按 .dat 原样导出（配合 --all 做全量备份）")
    ep.add_argument("--naming", choices=["orig", "md5"], default="orig", help="命名方式")

    vp = sub.add_parser("serve", help="启动本地 Web 界面（仅 127.0.0.1）")
    vp.add_argument("--port", type=int, default=8765)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"detect": cmd_detect, "scan": cmd_scan, "report": cmd_report,
                "export": cmd_export, "serve": cmd_serve}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
