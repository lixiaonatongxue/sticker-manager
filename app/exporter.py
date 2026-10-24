"""exporter：把选中的表情导出为带正确扩展名的标准文件。

安全护栏（硬性，不可绕过）：
1. 拒绝导出到微信数据目录内（探测规则 + 目录名兜底判据）；
2. 拒绝导出到任何被索引的源目录内（避免污染源目录、被下次扫描重复入库）；
3. 只读源文件（copyfile），绝不改动/删除源。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .indexer import StickerIndex
from .scanner import is_probably_wechat_dir


class ExportSafetyError(Exception):
    """导出目的地命中安全护栏。"""


@dataclass
class ExportResult:
    exported: list[str] = field(default_factory=list)   # 成功写出的目标文件
    skipped: list[dict] = field(default_factory=list)   # {id, path, reason}
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> dict:
        return {"exported": len(self.exported), "skipped": len(self.skipped),
                "errors": len(self.errors)}


def _check_dest(dest: Path, idx: StickerIndex) -> None:
    if is_probably_wechat_dir(dest):
        raise ExportSafetyError(
            f"目的地 {dest} 位于微信数据目录内，为避免破坏微信数据已拒绝导出。"
            "请选择微信目录之外的文件夹。"
        )
    # 目的地不能落在任何已索引的源目录里
    dest_abs = os.path.normcase(str(dest.resolve()))
    seen_roots: set[str] = set()
    for row in idx.conn.execute("SELECT path FROM stickers"):
        root = os.path.dirname(row["path"])
        if root in seen_roots:
            continue
        seen_roots.add(root)
        root_nc = os.path.normcase(root)
        if dest_nc_inside(dest_abs, root_nc):
            raise ExportSafetyError(
                f"目的地 {dest} 位于被扫描的表情源目录内，导出会污染源数据，已拒绝。"
                "请选择源目录之外的文件夹。"
            )


def dest_nc_inside(dest_nc: str, root_nc: str) -> bool:
    return dest_nc == root_nc or dest_nc.startswith(root_nc + os.sep)


def export_stickers(
    idx: StickerIndex,
    ids: list[int],
    dest: str | os.PathLike,
    naming: str = "orig",   # "orig"：原名+扩展名 | "md5"：md5 前缀命名（同名自动去重）
    include_unknown: bool = False,  # True 时 unknown/加密文件按 .dat 原样导出（备份模式）
) -> ExportResult:
    result = ExportResult()
    dest_path = Path(dest)
    dest_path.mkdir(parents=True, exist_ok=True)
    _check_dest(dest_path, idx)

    for sid in ids:
        s = idx.get(sid)
        if s is None:
            result.skipped.append({"id": sid, "path": "", "reason": "not_found"})
            continue
        # unknown = 微信新版加密表情等无法识别的格式；备份模式下按 .dat 原样带走
        if (not s["format"] or s["format"] == "unknown") and not include_unknown:
            result.skipped.append({"id": sid, "path": s["path"], "reason": "unknown_format"})
            continue
        ext = "dat" if (not s["format"] or s["format"] == "unknown") else s["format"]
        if not os.path.exists(s["path"]):
            result.skipped.append({"id": sid, "path": s["path"], "reason": "source_missing"})
            continue

        if naming == "md5":
            name = f"{s['md5'][:16]}.{ext}"
            target = dest_path / name
            if target.exists():  # 完全相同的文件只导出一次
                result.skipped.append({"id": sid, "path": s["path"], "reason": "same_md5_already_exported"})
                continue
        else:
            stem = Path(s["path"]).stem
            target = _unique_path(dest_path / f"{stem}.{ext}")

        try:
            shutil.copyfile(s["path"], target)
            result.exported.append(str(target))
        except OSError as e:
            result.errors.append(f"{s['path']}: {e}")
    return result


def _unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    for i in range(1, 1000):
        cand = p.with_name(f"{stem}-{i}{suffix}")
        if not cand.exists():
            return cand
    raise ExportSafetyError(f"无法为 {p.name} 找到可用文件名")
