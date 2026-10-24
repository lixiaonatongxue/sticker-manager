"""scanner：目录探测 + magic bytes 格式嗅探 + 文件遍历。

只做只读操作：列出文件、读文件头若干字节，绝不写入任何被扫描目录。
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# 嗅探时读取的文件头长度（RIFF/ftyp 判断最长相依于前 12 字节，留足余量）
HEAD_LEN = 16

# 小于该字节数的文件直接忽略（微信目录里的碎片/占位文件）
MIN_FILE_SIZE = 64

# 微信 3.x CustomEmotion 里的缩略图文件前缀，不作为独立表情入库
SKIP_PREFIXES = ("th_",)

# 聊天图片目录里每人均有的缩略图子目录（MsgAttach/<hash>/Thumb 等），
# 全是小尺寸重复图：跳过可大幅减少扫描量和假重复
SKIP_DIRNAMES = {"thumb"}


def sniff_format(head: bytes) -> str:
    """按文件头 magic bytes 识别真实格式，识别不了返回 "unknown"。"""
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"BM") and len(head) >= 6:
        return "bmp"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp":
        return "mp4"
    return "unknown"


# 微信经典图片 dat：整文件与一个随机字节异或（社区公开多年的方案，纯离线可解）
# 用 magic 前 3+ 字节一致性判定密钥，杜绝 2 字节 magic（BM）的误报
_DAT_MAGICS = (
    (b"GIF87a", "gif"), (b"GIF89a", "gif"), (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"), (b"BM\x00\x00\x00", "bmp"), (b"RIFF", None),
)


def sniff_dat_key(head: bytes) -> tuple[str, int] | None:
    """检测微信单字节 XOR 图片 dat，返回 (真实格式, 密钥)；非该格式返回 None。"""
    for magic, fmt in _DAT_MAGICS:
        if len(head) < len(magic):
            continue
        keys = {head[i] ^ magic[i] for i in range(len(magic))}
        if len(keys) != 1:
            continue
        k = keys.pop()
        if fmt:
            return fmt, k
        # RIFF....WEBP：再校验 8-11 字节异或后为 WEBP
        if len(head) >= 12 and bytes((b ^ k) for b in head[8:12]) == b"WEBP":
            return "webp", k
    # mp4: 偏移 4-7 为 ftyp
    if len(head) >= 8:
        for k in range(256):
            if all((head[4 + i] ^ k) == c for i, c in enumerate(b"ftyp")):
                return "mp4", k
    return None


def sniff_file(path: str | os.PathLike) -> str:
    """读取单个文件的头部并嗅探格式（只读，含 dat 识别）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(HEAD_LEN)
    except OSError:
        return "unknown"
    fmt = sniff_format(head)
    if fmt != "unknown":
        return fmt
    hit = sniff_dat_key(head)
    return hit[0] if hit else "unknown"


def sniff_full(path: str | os.PathLike) -> tuple[str, int | None]:
    """嗅探（格式, dat 密钥）。dat 密钥供解码管线复用。"""
    try:
        with open(path, "rb") as f:
            head = f.read(HEAD_LEN)
    except OSError:
        return "unknown", None
    fmt = sniff_format(head)
    if fmt != "unknown":
        return fmt, None
    hit = sniff_dat_key(head)
    if hit:
        return hit[0], hit[1]
    return "unknown", None


@dataclass
class StickerFile:
    path: str
    format: str
    size: int
    mtime: float
    dat_key: int | None = None  # 微信单字节 XOR dat 的密钥（嗅探时得出）


@dataclass
class ScanResult:
    root: str
    files: list[StickerFile] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)  # format -> 数量（含 unknown）
    truncated: bool = False  # 因 max_files 限额提前停止（受限测试模式）

    @property
    def total(self) -> int:
        return len(self.files)


def scan_directory(
    root: str | os.PathLike,
    max_files: int | None = None,
    min_size: int = MIN_FILE_SIZE,
    skip_prefixes: tuple[str, ...] = SKIP_PREFIXES,
) -> ScanResult:
    """遍历目录，识别每个文件的真实格式。

    max_files：最多收录多少个文件，用于受限测试/抽样，触顶时 truncated=True。
    """
    result = ScanResult(root=str(root))
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过符号链接/联接目录（防 OneDrive/备份联接死循环）和缩略图目录
        dirnames[:] = [
            d for d in dirnames
            if not os.path.islink(os.path.join(dirpath, d)) and d.lower() not in SKIP_DIRNAMES
        ]
        for name in sorted(filenames):
            if name.lower().startswith(skip_prefixes):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            if st.st_size < min_size:
                continue
            fmt, dat_key = sniff_full(full)
            result.files.append(StickerFile(path=full, format=fmt, size=st.st_size,
                                            mtime=st.st_mtime, dat_key=dat_key))
            result.counts[fmt] = result.counts.get(fmt, 0) + 1
            if max_files is not None and len(result.files) >= max_files:
                result.truncated = True
                return result
    return result


def scan_multiple(
    roots: list[str | os.PathLike],
    max_files: int | None = None,
    min_size: int = MIN_FILE_SIZE,
    skip_prefixes: tuple[str, ...] = SKIP_PREFIXES,
    on_root=None,
) -> ScanResult:
    """扫描多个目录并合并结果（max_files 是跨目录的总限额）。

    用于"无 path 扫描 = 自动扫全部探测到的微信目录"：多账号/多版本
    一起入库，还能顺带做跨目录去重。on_root(i, n, root) 在进入每个目录前回调。
    """
    merged = ScanResult(root=";".join(str(r) for r in roots))
    for i, r in enumerate(roots):
        if on_root:
            on_root(i, len(roots), str(r))
        remain = (max_files - len(merged.files)) if max_files is not None else None
        if remain is not None and remain <= 0:
            merged.truncated = True
            break
        sr = scan_directory(r, max_files=remain, min_size=min_size, skip_prefixes=skip_prefixes)
        merged.files.extend(sr.files)
        for k, v in sr.counts.items():
            merged.counts[k] = merged.counts.get(k, 0) + v
        if sr.truncated:
            merged.truncated = True
            break
    return merged


def iter_files(root: str | os.PathLike) -> Iterator[str]:
    """简单列出目录下全部文件路径（不嗅探），供计数等用途。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            yield os.path.join(dirpath, name)


# ---------------------------------------------------------------- 目录探测

@dataclass
class DetectedDir:
    path: str
    label: str      # 如 "微信 3.x"
    rule_id: str    # 如 "wechat3x"
    n_files: int    # 目录内文件数（快速 scandir 计数，不递归）


def default_rules_path() -> Path:
    """定位 rules/paths.json：源码运行时在仓库根，打包后与应用同目录。"""
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "rules" / "paths.json", here / "rules" / "paths.json"):
        if cand.exists():
            return cand
    return Path("rules") / "paths.json"


def detect_wechat_dirs(
    rules_path: str | os.PathLike | None = None,
    home: str | os.PathLike | None = None,
) -> list[DetectedDir]:
    """按规则表自动探测微信表情目录；探测结果可能为空（用户随后手动选文件夹）。

    home 仅用于测试时替换 "~" 的展开目标。
    """
    rp = Path(rules_path) if rules_path else default_rules_path()
    try:
        rules = json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    found: dict[str, DetectedDir] = {}
    for root_rule in rules.get("roots", []):
        bases = list(root_rule.get("base", [])) + _config_derived_bases()
        for base in bases:
            base_path = Path(_expanduser(base, home))
            if not base_path.is_dir():
                continue
            for pattern in root_rule.get("patterns", []):
                for hit in glob.glob(str(base_path / pattern)):
                    p = Path(hit)
                    if not p.is_dir():
                        continue
                    n = sum(1 for _ in os.scandir(p))
                    d = DetectedDir(path=str(p), label=root_rule.get("label", root_rule.get("id", "?")),
                                    rule_id=root_rule.get("id", "?"), n_files=n)
                    # 同一目录被多条规则命中时，保留文件数信息即可，不去重报警
                    found.setdefault(str(p).lower(), d)
    return list(found.values())


def _config_derived_bases() -> list[str]:
    """从微信 4.x 客户端配置里挖自定义数据根目录（只读）。

    实测（2026-10）：%APPDATA%/Tencent/xwechat/config/*.ini 首行是用户自选的
    数据目录（如 E:\\wechat），其下同时存在 xwechat_files（4.x）与
    WeChat Files（3.x）。读取失败静默返回空。
    """
    bases: list[str] = []
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return bases
    cfg_dir = Path(appdata) / "Tencent" / "xwechat" / "config"
    if not cfg_dir.is_dir():
        return bases
    for ini in cfg_dir.glob("*.ini"):
        try:
            lines = ini.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        if lines and lines[0].strip() and Path(lines[0].strip()).is_dir():
            bases.append(lines[0].strip())
    return list(dict.fromkeys(bases))  # 去重保序


def is_probably_wechat_dir(path: str | os.PathLike) -> bool:
    """判断某路径是否位于微信数据目录内或与其同级结构（exporter 的安全护栏用）。

    两条判据：
    1. 路径在某个已探测到的微信表情目录内（含等于）；
    2. 路径的某一级目录名是 WeChat Files / xwechat_files（未探测到也兜底拦截）。
    注意：不拦上层公共目录（如 Documents），只拦微信数据目录本身及其内部。
    """
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    for d in detect_wechat_dirs():
        try:
            root_p = Path(d.path).resolve()
        except OSError:
            continue
        if p == root_p or root_p in p.parents:
            return True
    return any(part.lower() in ("wechat files", "xwechat_files") for part in p.parts)


def _expanduser(p: str, home: str | os.PathLike | None) -> str:
    if p.startswith("~"):
        base = Path(home) if home else Path.home()
        return str(base / p[2:] if p.startswith("~/") else base)
    return p
