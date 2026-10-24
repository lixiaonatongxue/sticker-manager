"""API 集成测试：scan → status → stickers → duplicates → thumbnail → export。"""

from __future__ import annotations

import time

import time

from fastapi.testclient import TestClient

from app.server import app

from .conftest import make_image_file  # noqa: F401  (client fixture via conftest)


def _wait_scan_done(c, timeout=10):
    for _ in range(timeout * 20):
        st = c.get("/api/scan/status").json()
        if not st["running"] and (st["last_stats"] or st["last_error"]):
            return st
        time.sleep(0.05)
    raise AssertionError("scan did not finish: " + str(c.get('/api/scan/status').json()))


def test_full_api_flow(client):
    c, root, tmp = client

    # 扫描（后台任务）
    r = c.post("/api/scan", json={"path": str(root)})
    assert r.status_code == 200
    st = _wait_scan_done(c)
    assert st["last_error"] is None
    assert st["last_stats"]["added"] == 3

    # 状态与浏览
    status = c.get("/api/status").json()
    assert status["summary"]["total"] == 3
    page = c.get("/api/stickers", params={"page": 1, "per_page": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    by_fmt = c.get("/api/stickers", params={"format": "png"}).json()
    assert by_fmt["total"] == 1

    # 去重：一组（a/a_copy），b 独立
    r = c.post("/api/duplicates/compute", json={"threshold": 8})
    assert r.json()["n_groups"] == 1
    dups = c.get("/api/duplicates").json()
    assert dups["summary"]["dup_files"] == 1
    assert len(dups["groups"][0]["members"]) == 2

    # 缩略图
    sid = page["items"][0]["id"]
    r = c.get(f"/api/thumbnail/{sid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"

    # 标签
    r = c.post(f"/api/stickers/{sid}/tags", json={"tags": ["猫", "开心"]})
    assert r.json()["tags"] == "猫,开心"
    assert c.get("/api/tags").json() == [{"tag": "猫", "count": 1}, {"tag": "开心", "count": 1}]
    assert c.get("/api/stickers", params={"tag": "猫"}).json()["total"] == 1

    # 导出成功 + 安全护栏
    dest = tmp / "exports"
    r = c.post("/api/export", json={"ids": [sid], "dest": str(dest)})
    assert r.status_code == 200 and r.json()["summary"]["exported"] == 1
    r = c.post("/api/export", json={"ids": [sid], "dest": str(root / "sub")})
    assert r.status_code == 400
    assert "源目录" in r.json()["detail"]

    # autotag 占位
    assert c.post("/api/autotag").status_code == 501


def test_scan_detects_no_dir_error(client, tmp_path):
    c, root, tmp = client
    # 清空索引后不带 path 扫描：探测不到目录 → last_error
    import app.server as srv
    orig = srv.detect_wechat_dirs
    srv.detect_wechat_dirs = lambda **kw: []
    try:
        r = c.post("/api/scan", json={})
        assert r.status_code == 200
        st = _wait_scan_done(c)
        assert "未探测到" in st["last_error"]
    finally:
        srv.detect_wechat_dirs = orig


def test_scan_multiple_detected_dirs_scans_all(client, tmp_path):
    """探测到多个目录时：不再让用户指定，直接全部扫描。"""
    c, root, tmp = client
    from app.scanner import DetectedDir
    import app.server as srv

    class FakeDir:
        def __init__(self, p):
            from app.scanner import DetectedDir as D
            self.path, self.label, self.rule_id, self.n_files = p, "微信 3.x", "wechat3x", 1

    # 造第二个目录
    other = tmp / "OtherEmotion"
    other.mkdir()
    make_image_file(other / "z", "gif", size=64, hue=99)

    orig = srv.detect_wechat_dirs
    srv.detect_wechat_dirs = lambda **kw: [
        FakeDir(str(root)), FakeDir(str(other))]
    try:
        assert c.post("/api/scan", json={}).status_code == 200
        st = _wait_scan_done(c)
        assert st["last_error"] is None
        assert st["last_stats"]["dirs"] == 2
        total = c.get("/api/status").json()["summary"]["total"]
        n_root = len(list((root).iterdir()))
        assert total == n_root + 1  # 两个目录全部入库
    finally:
        srv.detect_wechat_dirs = orig
