"""deduper：两级去重 —— MD5 精确去重 → pHash 视觉近似聚类。

设计约束（对应方案的合规边界）：
- 本模块只做"识别与标记"，不提供任何删除微信目录文件的功能；
- keeper = 组内最优（分辨率 → 帧数 → 文件大小），供"导出精选"用。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .indexer import StickerIndex

DEFAULT_THRESHOLD = 8  # pHash 汉明距离阈值，≤ 此值判为近似（开放为设置项）


@dataclass
class DupGroup:
    group_id: int
    kind: str            # "exact"（组内 md5 全同）| "near"
    members: list        # sticker dict 列表，keeper 排最前
    keeper_id: int

    @property
    def extra_count(self) -> int:
        return len(self.members) - 1


@dataclass
class DedupReport:
    groups: list[DupGroup] = field(default_factory=list)
    total_indexed: int = 0

    @property
    def dup_files(self) -> int:
        """可精简的文件数 = 各组人数 - 1 之和"""
        return sum(g.extra_count for g in self.groups)

    def summary(self) -> dict:
        return {
            "total_indexed": self.total_indexed,
            "n_groups": len(self.groups),
            "n_exact": sum(1 for g in self.groups if g.kind == "exact"),
            "n_near": sum(1 for g in self.groups if g.kind == "near"),
            "dup_files": self.dup_files,
        }


def _keeper_key(s: dict):
    """keeper 排序键：分辨率 → 帧数 → 文件大小；id 倒序保证稳定排序。"""
    return ((s["width"] or 0) * (s["height"] or 0), s["frames"] or 0, s["size"], -s["id"])


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def compute_duplicates(idx: StickerIndex, threshold: int = DEFAULT_THRESHOLD) -> DedupReport:
    """全量重算重复组并写入 dup_groups 表（整表替换，保证与索引一致）。"""
    stickers = idx.all_stickers()
    report = DedupReport(total_indexed=len(stickers))

    # ---- 1) MD5 精确组（无 phash 的 mp4/unknown 也能参与）
    by_md5: dict[str, list[dict]] = {}
    for s in stickers:
        if s["md5"]:
            by_md5.setdefault(s["md5"], []).append(s)
    exact_ids: set[int] = set()
    for members in by_md5.values():
        if len(members) > 1:
            exact_ids.update(m["id"] for m in members)

    # ---- 2) pHash 近似聚类（numpy uint64 + 位计数，包含精确组，距离 0 必然同类）
    hashed = [s for s in stickers if s["phash"]]
    uf = _UnionFind(len(hashed))
    if len(hashed) >= 2:
        arr = np.array([int(s["phash"], 16) for s in hashed], dtype=np.uint64)
        for i in range(len(arr) - 1):
            dist = np.bitwise_count(arr[i] ^ arr[i + 1:])
            for j in np.nonzero(dist <= threshold)[0]:
                uf.union(i, int(j) + i + 1)

    clusters: dict[int, list[dict]] = {}
    for i, s in enumerate(hashed):
        clusters.setdefault(uf.find(i), []).append(s)

    # ---- 3) 组装：每组成员排序、标记 keeper、区分类型
    groups: list[DupGroup] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        members = sorted(members, key=_keeper_key, reverse=True)
        keeper = members[0]
        kind = "exact" if len({m["md5"] for m in members}) == 1 else "near"
        groups.append(DupGroup(group_id=0, kind=kind, members=members, keeper_id=keeper["id"]))
    # 组间排序：大的重复组排前面
    groups.sort(key=lambda g: (-g.extra_count, -g.keeper_id))

    # 持久化到 dup_groups
    idx.conn.execute("DELETE FROM dup_groups")
    for gid, g in enumerate(groups, start=1):
        g.group_id = gid
        idx.conn.executemany(
            "INSERT INTO dup_groups (group_id, sticker_id, is_keeper) VALUES (?,?,?)",
            [(gid, m["id"], 1 if m["id"] == g.keeper_id else 0) for m in g.members],
        )
    idx.conn.commit()

    report.groups = groups
    return report


def load_groups(idx: StickerIndex) -> list[DupGroup]:
    """从 dup_groups 表读回已计算好的分组（服务端列表页用）。"""
    stickers = {s["id"]: s for s in idx.all_stickers()}
    rows = idx.conn.execute(
        "SELECT group_id, sticker_id, is_keeper FROM dup_groups ORDER BY group_id").fetchall()
    by_gid: dict[int, list[dict]] = {}
    for r in rows:
        s = stickers.get(r["sticker_id"])
        if s is not None:
            by_gid.setdefault(r["group_id"], []).append(s)
    groups = []
    for gid, members in by_gid.items():
        members = sorted(members, key=_keeper_key, reverse=True)  # keeper 恒为首位
        kind = "exact" if len({m["md5"] for m in members}) == 1 else "near"
        groups.append(DupGroup(gid, kind, members, members[0]["id"]))
    groups.sort(key=lambda g: (-g.extra_count, -g.keeper_id))
    return groups
