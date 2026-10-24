"""FastAPI 本地服务：仅绑定 127.0.0.1，不对外网开放（合规承诺）。

启动：python -m app.server  或  sticker-manager serve
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from . import __version__
from .deduper import DEFAULT_THRESHOLD, compute_duplicates, load_groups
from .exporter import ExportSafetyError, export_stickers
from .indexer import IMAGE_FORMATS, StickerIndex, default_db_path
from .scanner import detect_wechat_dirs, scan_multiple

app = FastAPI(title="Sticker Manager", version=__version__)

# 环境变量可覆盖 DB 路径（测试/多库切换用）；None = 默认 ~/.sticker-manager/stickers.db
import os as _os
app.state.db_path = _os.environ.get("STICKER_MANAGER_DB")
app.state.web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"

# ------------------------------------------------------------------ 扫描任务

_scan_lock = threading.Lock()
scan_state = {
    "running": False, "done": 0, "total": 0,
    "last_error": None, "last_stats": None, "finished_at": None,
}


def _open_index(request: Request) -> StickerIndex:
    db = request.app.state.db_path
    return StickerIndex(Path(db) if db else default_db_path())


def _run_scan(path: str | None, max_files: int | None, db_path) -> None:
    try:
        # 无 path = 自动扫全部探测到的微信目录（多账号/多版本一起入库）
        roots = [path] if path else [d.path for d in detect_wechat_dirs()]
        if not roots:
            scan_state["last_error"] = "未探测到微信表情目录，请手动指定 path"
            return
        result = scan_multiple(roots, max_files=max_files)
        scan_state["total"] = result.total
        idx = StickerIndex(Path(db_path) if db_path else default_db_path())
        try:
            stats = idx.index_result(
                result,
                progress=lambda i, n: scan_state.update(done=i, total=n),
            )
            scan_state["last_stats"] = {
                "added": stats.added, "updated": stats.updated,
                "skipped": stats.skipped, "errors": len(stats.errors),
                "truncated": result.truncated, "counts": result.counts,
                "dirs": len(roots),
            }
        finally:
            idx.close()
    except Exception as e:  # 扫描线程兜底：任何异常都落到状态里
        scan_state["last_error"] = str(e)
    finally:
        scan_state["running"] = False
        import time
        scan_state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


class ScanRequest(BaseModel):
    path: str | None = None
    max_files: int | None = None


@app.post("/api/scan")
def start_scan(req: ScanRequest, request: Request, bg: BackgroundTasks):
    if scan_state["running"]:
        raise HTTPException(409, "扫描进行中，请等待完成")
    with _scan_lock:
        if scan_state["running"]:
            raise HTTPException(409, "扫描进行中")
        scan_state.update(running=True, done=0, total=0, last_error=None, last_stats=None)
        bg.add_task(_run_scan, req.path, req.max_files, request.app.state.db_path)
    return {"ok": True, "message": "扫描已开始"}


@app.get("/api/scan/status")
def scan_status():
    return scan_state


# ------------------------------------------------------------------ 元信息

@app.get("/api/status")
def status(request: Request):
    idx = _open_index(request)
    try:
        return {
            "version": __version__,
            "db_path": str(idx.db_path),
            "summary": idx.stats_summary(),
            "detected_dirs": [
                {"path": d.path, "label": d.label, "rule_id": d.rule_id, "n_files": d.n_files}
                for d in detect_wechat_dirs()
            ],
        }
    finally:
        idx.close()


@app.get("/api/detect")
def detect():
    return [{"path": d.path, "label": d.label, "rule_id": d.rule_id, "n_files": d.n_files}
            for d in detect_wechat_dirs()]


# ------------------------------------------------------------------ 表情浏览

@app.get("/api/stickers")
def stickers(request: Request, page: int = 1, per_page: int = 100,
             format: str | None = None, tag: str | None = None, q: str | None = None):
    idx = _open_index(request)
    try:
        return idx.list_stickers(page=page, per_page=min(per_page, 500),
                                 fmt=format, tag=tag, q=q)
    finally:
        idx.close()


@app.get("/api/stickers/{sticker_id}")
def sticker_detail(sticker_id: int, request: Request):
    idx = _open_index(request)
    try:
        s = idx.get(sticker_id)
        if not s:
            raise HTTPException(404, "不存在")
        return s
    finally:
        idx.close()


class TagsRequest(BaseModel):
    tags: list[str]


@app.post("/api/stickers/{sticker_id}/tags")
def set_tags(sticker_id: int, req: TagsRequest, request: Request):
    idx = _open_index(request)
    try:
        if not idx.set_tags(sticker_id, req.tags):
            raise HTTPException(404, "不存在")
        return idx.get(sticker_id)
    finally:
        idx.close()


@app.get("/api/tags")
def tags(request: Request):
    idx = _open_index(request)
    try:
        return idx.all_tags()
    finally:
        idx.close()


# ------------------------------------------------------------------ 去重

class ComputeRequest(BaseModel):
    threshold: int = DEFAULT_THRESHOLD


@app.post("/api/duplicates/compute")
def duplicates_compute(req: ComputeRequest, request: Request):
    idx = _open_index(request)
    try:
        report = compute_duplicates(idx, threshold=req.threshold)
        return report.summary()
    finally:
        idx.close()


@app.get("/api/duplicates")
def duplicates(request: Request):
    idx = _open_index(request)
    try:
        groups = load_groups(idx)
        return {
            "summary": {"n_groups": len(groups),
                        "n_exact": sum(1 for g in groups if g.kind == "exact"),
                        "n_near": sum(1 for g in groups if g.kind == "near"),
                        "dup_files": sum(g.extra_count for g in groups)},
            "groups": [
                {"group_id": g.group_id, "kind": g.kind, "keeper_id": g.keeper_id,
                 "members": g.members}
                for g in groups
            ],
        }
    finally:
        idx.close()


# ------------------------------------------------------------------ 缩略图

@app.get("/api/thumbnail/{sticker_id}")
def thumbnail(sticker_id: int, request: Request):
    idx = _open_index(request)
    try:
        s = idx.get(sticker_id)
        if not s:
            raise HTTPException(404, "不存在")
        if s["format"] not in IMAGE_FORMATS:
            raise HTTPException(404, "该格式无预览（mp4/unknown）")
        thumbs = idx.db_path.parent / "thumbs"
        thumbs.mkdir(exist_ok=True)
        target = thumbs / f"{s['id']}_{int(s['mtime'] or 0)}.webp"
        if not target.exists():
            with Image.open(s["path"]) as img:
                img.thumbnail((320, 320))
                img.save(target, format="WEBP")
        return FileResponse(target, media_type="image/webp")
    finally:
        idx.close()


# ------------------------------------------------------------------ 导出

class ExportRequest(BaseModel):
    ids: list[int] = []
    dest: str
    naming: str = "orig"
    include_unknown: bool = False  # unknown/加密文件按 .dat 原样导出
    all: bool = False              # 备份模式：导出索引内全部表情


@app.post("/api/export")
def export(req: ExportRequest, request: Request):
    idx = _open_index(request)
    try:
        ids = [r["id"] for r in idx.all_stickers()] if req.all else req.ids
        if not ids:
            raise HTTPException(400, "没有可导出的表情（索引为空或 ids 为空）")
        try:
            r = export_stickers(idx, ids, req.dest, naming=req.naming,
                                include_unknown=req.include_unknown)
        except ExportSafetyError as e:
            raise HTTPException(400, str(e))
        return {"summary": r.summary(), "exported": r.exported,
                "skipped": r.skipped, "errors": r.errors}
    finally:
        idx.close()


@app.post("/api/autotag")
def autotag():
    raise HTTPException(501, "自动打标签是 v0.3 功能，尚未实现")


# ------------------------------------------------------------------ 前端静态资源

_dist = app.state.web_dist
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")


def main(host: str = "127.0.0.1", port: int | None = None) -> None:
    import uvicorn
    port = port or int(_os.environ.get("STICKER_MANAGER_PORT", "8765"))
    print(f"Sticker Manager v{__version__}  ->  http://{host}:{port}（仅本机访问）")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
