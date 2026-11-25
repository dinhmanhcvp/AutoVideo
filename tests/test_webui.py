"""Giao diện web: chạy server thật trên cổng ngẫu nhiên, gọi API như trình duyệt."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml
from PIL import Image

from autovideo.webui.server import make_server


def start(root: Path, token=None):
    srv = make_server(root, "127.0.0.1", 0, token)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def call(base, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req) as r:
        raw = r.read()
        return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw


@pytest.fixture
def site(tmp_path):
    item = tmp_path / "ready" / "2026-11-24_tham-thich"
    item.mkdir(parents=True)
    (item / "video.mp4").write_bytes(bytes(range(256)) * 40)  # 10.240 byte
    for i, color in enumerate(["red", "green", "blue"], 1):
        Image.new("RGB", (64, 36), color).save(item / ("thumbnail.jpg" if i == 1 else f"thumbnail_{i}.jpg"))
    (item / "titles.json").write_text(json.dumps(["T1", "T2", "T3"]), encoding="utf-8")
    for name, text in {"title.txt": "T1", "description.txt": "mô tả", "tags.txt": "a, b",
                       "pinned_comment.txt": "Bạn nghĩ sao?"}.items():
        (item / name).write_text(text, encoding="utf-8")
    (item / "analysis.json").write_text(json.dumps({"score": 7.9, "logline_vi": "x"}), encoding="utf-8")
    (item / "cost.json").write_text(json.dumps({"total_usd": 1.2}), encoding="utf-8")
    (tmp_path / "secret.txt").write_text("không được lộ", encoding="utf-8")
    srv, base = start(tmp_path)
    yield tmp_path, base, item
    srv.shutdown()


def test_index_and_overview(site):
    root, base, _ = site
    assert b"AutoVideo" in call(base, "/")
    ov = call(base, "/api/overview")
    assert ov["counts"] == {"pending": 1} and ov["cost_month"] in (0, 1.2) and ov["total"] == 1
    assert any(t["enabled"] for t in ov["topics"])


def test_ready_item_variant_and_text_edit(site):
    root, base, item = site
    items = call(base, "/api/ready")
    assert items[0]["title"] == "T1" and items[0]["score"] == 7.9
    call(base, f"/api/ready/{item.name}/variant", {"n": 3})
    assert (item / "title.txt").read_text(encoding="utf-8") == "T3"
    assert Image.open(item / "thumbnail.jpg").getpixel((5, 5))[2] > 200
    call(base, f"/api/ready/{item.name}/variant", {"n": 1})  # quay lại phương án gốc
    assert (item / "title.txt").read_text(encoding="utf-8") == "T1"
    assert Image.open(item / "thumbnail.jpg").getpixel((5, 5))[0] > 200
    call(base, f"/api/ready/{item.name}/text", {"file": "description.txt", "content": "mới"})
    assert (item / "description.txt").read_text(encoding="utf-8") == "mới"
    with pytest.raises(urllib.error.HTTPError) as e:
        call(base, f"/api/ready/{item.name}/text", {"file": "../../secret.txt", "content": "x"})
    assert e.value.code == 400


def test_reject_restore_and_manual(site):
    root, base, item = site
    call(base, f"/api/ready/{item.name}/reject", {})
    assert (root / "ready" / "_rejected" / item.name).exists()
    assert call(base, "/api/ready")[0]["status"] == "rejected"
    call(base, f"/api/ready/{item.name}/restore", {})
    call(base, f"/api/ready/{item.name}/manual", {})
    assert call(base, "/api/ready")[0]["status"] == "published_manual"


def test_publish_requires_youtube_enabled(site):
    root, base, item = site
    with pytest.raises(urllib.error.HTTPError) as e:
        call(base, f"/api/ready/{item.name}/publish", {})
    assert e.value.code == 400 and "YouTube" in json.loads(e.value.read())["error"]


def test_file_serving_range_and_traversal(site):
    root, base, item = site
    rel = f"ready/{item.name}/video.mp4"
    req = urllib.request.Request(f"{base}/files?p={rel}", headers={"Range": "bytes=100-199"})
    with urllib.request.urlopen(req) as r:
        assert r.status == 206 and r.headers["Content-Range"] == "bytes 100-199/10240"
        assert r.read() == bytes(range(100, 200))
    for bad in ("secret.txt", "../etc/passwd", f"ready/{item.name}/../../secret.txt"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/files?p={bad}")
        assert e.value.code == 403


def test_settings_save_topics_and_keys(site, monkeypatch):
    root, base, _ = site
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    call(base, "/api/config", {"channel": {"name": "Kênh Mới"}, "quality": {"min_score": 7},
                               "topics_enabled": {"ngon_tinh_hao_mon": False, "hai_huoc_gia_dinh": True}})
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    assert saved["channel"]["name"] == "Kênh Mới" and saved["quality"]["min_score"] == 7
    enabled = [t["name"] for t in saved["topics"] if t["enabled"]]
    assert enabled == ["hai_huoc_gia_dinh"]
    call(base, "/api/config", {"channel": {"title_template": "{story_title}"}})  # lưu lần 2 giữ lần 1
    saved = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    assert saved["channel"] == {"name": "Kênh Mới", "title_template": "{story_title}"}
    r = call(base, "/api/env", {"GROQ_API_KEY": "gsk-test", "EVIL": "x"})
    assert r["keys"]["GROQ_API_KEY"] is True
    env = (root / ".env").read_text(encoding="utf-8")
    assert "GROQ_API_KEY=gsk-test" in env and "EVIL" not in env
    cfg = call(base, "/api/config")
    assert "gsk-test" not in json.dumps(cfg)  # không bao giờ trả khóa về trình duyệt
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def test_inbox(site):
    root, base, _ = site
    call(base, "/api/inbox", {"topic": "ngon_tinh_hao_mon", "text": "她推开门。" * 100, "name": "truyen 1"})
    assert (root / "inbox" / "ngon_tinh_hao_mon" / "truyen-1.txt").exists()
    assert call(base, "/api/inbox") == ["inbox/ngon_tinh_hao_mon/truyen-1.txt"]
    with pytest.raises(urllib.error.HTTPError):
        call(base, "/api/inbox", {"topic": "khong_co", "text": "x" * 500})


def test_task_runs_subprocess_and_streams_log(site):
    import time

    root, base, _ = site
    task = call(base, "/api/tasks", {"kind": "doctor"})
    for _ in range(60):
        r = call(base, f"/api/tasks/{task['id']}/log?offset=0")
        if r["task"]["status"] != "running":
            break
        time.sleep(0.5)
    assert "Hệ thống" in r["text"] and r["task"]["status"] in ("done", "failed")
    assert call(base, "/api/tasks")[0]["id"] == task["id"]


def test_lan_mode_requires_token(tmp_path):
    srv, base = start(tmp_path, token="abc123")
    try:
        assert b"AutoVideo" in call(base, "/")  # trang chính tải được (chưa có dữ liệu)
        with pytest.raises(urllib.error.HTTPError) as e:
            call(base, "/api/overview")
        assert e.value.code == 401
        assert call(base, "/api/overview", headers={"X-Token": "abc123"})["total"] == 0
        assert call(base, "/api/overview", headers={"Cookie": "av_token=abc123"})["total"] == 0
    finally:
        srv.shutdown()
