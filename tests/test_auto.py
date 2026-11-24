import json
from pathlib import Path

from autovideo import auto, ff, render, thumbnail
from autovideo.config import load_config


def fake_search_factory(db):
    def fake_search(kw, site, limit):
        return db.get((kw, site), [])[:limit]
    return fake_search


TOPIC = {"name": "t", "keywords": ["k1", "k2"], "sites": ["bilisearch", "ytsearch"],
         "min_minutes": 10, "max_minutes": 60, "genre": "tam_su", "tts": {"voice": "vi-VN-NamMinhNeural"}}

DB = {
    ("k1", "bilisearch"): [
        {"url": "https://www.bilibili.com/video/BV1aaaaaaaaa?p=1", "title": "【有声书】故事A", "duration": 1800},
        {"url": "https://www.bilibili.com/video/BV1bbbbbbbbb", "title": "短片", "duration": 60},  # quá ngắn
    ],
    ("k1", "ytsearch"): [
        {"url": "https://www.youtube.com/watch?v=XYZ&t=3", "title": "故事B 完结", "duration": 2400},
    ],
    ("k2", "bilisearch"): [
        {"url": "https://www.bilibili.com/video/BV1aaaaaaaaa", "title": "故事A", "duration": 1800},  # trùng
    ],
}


def test_topic_config_overrides():
    cfg = load_config()
    tcfg = auto.topic_config(cfg, TOPIC)
    assert tcfg["genre"] == "tam_su"
    assert tcfg["tts"]["voice"] == "vi-VN-NamMinhNeural"
    assert tcfg["tts"]["chunk_words"] == cfg["tts"]["chunk_words"]  # các khóa khác giữ nguyên
    assert "keywords" not in tcfg


def test_discover_filters_dedupes_and_interleaves():
    found = auto.discover(TOPIC, 2, fake_search_factory(DB))
    keys = [auto.canonical_key(c["url"]) for c in found]
    assert keys == ["bilibili:BV1aaaaaaaaa", "youtube:XYZ"]


def test_history_skips_done_and_same_title(tmp_path):
    h = auto.History(tmp_path / "h.json")
    a = {"url": "https://www.bilibili.com/video/BV1aaaaaaaaa", "title": "【有声书】故事A 完结版"}
    h.mark(a, "done", "t")
    assert h.should_skip(a, 2) == "done"
    reup = {"url": "https://www.youtube.com/watch?v=Q", "title": "故事A完结版"}
    assert h.should_skip(reup, 2) == "trùng tiêu đề"
    b = {"url": "https://x.com/1", "title": "khác"}
    h.mark(b, "failed", "t")
    assert h.should_skip(b, 2) is None
    h.mark(b, "failed", "t")
    assert h.should_skip(b, 2) == "quá số lần lỗi"
    assert auto.History(tmp_path / "h.json").should_skip(a, 2) == "done"  # đã lưu ra đĩa


def test_run_auto_exports_ready_folder(tmp_path, monkeypatch):
    class FakeJob:
        def __init__(self, source, cfg, name=None):
            self.cfg = cfg
            self.dir = tmp_path / "out" / auto.canonical_key(source).replace(":", "_")
            self.dir.mkdir(parents=True, exist_ok=True)

        def p(self, n):
            return self.dir / n

        def run(self, stages=None):
            if stages == ["fetch"]:
                self.p("source_info.json").write_text(json.dumps({"duration": 1800}))
                return
            assert self.cfg["genre"] == "tam_su"  # nhận đúng config theo chủ đề
            self.p("video.mp4").write_bytes(b"v")
            self.p("thumbnail.jpg").write_bytes(b"t")
            self.p("youtube_description.txt").write_text("mô tả", encoding="utf-8")
            self.p("metadata.json").write_text(json.dumps(
                {"youtube_title": "Chuyện Tình Đêm Mưa", "tags": ["a", "b"]}), encoding="utf-8")

    monkeypatch.setattr(auto, "Job", FakeJob)
    cfg = load_config(overrides={"auto": {"ready_dir": str(tmp_path / "ready"),
                                          "history_file": str(tmp_path / "h.json")}})
    cfg["topics"] = [TOPIC]
    produced = auto.run_auto(cfg, per_topic=2, search_fn=fake_search_factory(DB))
    assert len(produced) == 2
    d = produced[0]
    assert d.name.endswith("chuyen-tinh-dem-mua")
    assert (d / "title.txt").read_text(encoding="utf-8") == "Chuyện Tình Đêm Mưa"
    assert (d / "tags.txt").read_text(encoding="utf-8") == "a, b"
    # Lần chạy sau: không làm lại truyện cũ
    assert auto.run_auto(cfg, per_topic=2, search_fn=fake_search_factory(DB)) == []


def test_thumbnail_mode_render(tmp_path):
    bg = thumbnail.placeholder_background("x", tmp_path / "bg.png", size=(640, 360))
    tcfg = dict(load_config()["thumbnail"], badge="Đêm Nghe Truyện")
    thumb = thumbnail.compose(bg, ["Chuyện Tình", "Đêm Mưa"], tmp_path / "t.jpg", tcfg)
    voice = tmp_path / "v.wav"
    ff.run(["-f", "lavfi", "-i", "sine=frequency=300", "-t", 3, voice])
    rcfg = load_config(overrides={"render": {
        "mode": "thumbnail", "resolution": [320, 180], "fps": 15, "encoder": "libx264",
        "lead_in": 0.5, "tail": 0.5, "audio": {"music_dir": str(tmp_path / "none")}}})["render"]
    work = tmp_path / "w"
    work.mkdir()
    out = render.render(voice, [thumb], work, rcfg)
    assert abs(ff.duration(out) - 4.0) < 0.4


def test_still_loop_renders_little_but_fills_duration(tmp_path):
    img = thumbnail.placeholder_background("x", tmp_path / "x.png", size=(640, 360))
    rcfg = load_config(overrides={"render": {"resolution": [320, 180], "fps": 12, "encoder": "libx264",
                                             "still": {"zoom_period": 2, "loop": True, "upscale": 1.5}}})["render"]
    out = render.still_track([img, img], 13.0, tmp_path / "bg.mp4", rcfg, "libx264")
    assert abs(ff.duration(out) - 13.0) < 0.3
    rendered = sorted(p.name for p in tmp_path.glob("seg_*.mp4"))
    assert rendered == ["seg_00_a.mp4", "seg_00_b.mp4", "seg_01_a.mp4", "seg_01_b.mp4"]  # chỉ 4 clip 2s


def test_cloud_asr_chunks_offsets_and_cache(tmp_path, monkeypatch):
    from autovideo import asr

    audio = tmp_path / "a.m4a"
    ff.run(["-f", "lavfi", "-i", "sine=frequency=300", "-t", 150, audio])
    calls = []

    def fake_groq(path, cfg):
        calls.append(path.name)
        return [{"start": 0.0, "end": 5.0, "text": "你好。"}, {"start": 8.0, "end": 10.0, "text": "再见。"}]

    monkeypatch.setattr(asr, "_groq_chunk", fake_groq)
    cfg = {"engine": "groq", "chunk_minutes": 1}
    text = asr.transcribe(audio, tmp_path / "t.json", cfg)
    segs = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))["segments"]
    assert len(calls) == 3 and len(segs) == 6
    assert abs(segs[2]["start"] - 60.0) < 0.5  # offset đoạn 2 cộng đúng
    assert text.count("你好") == 3
    asr.transcribe(audio, tmp_path / "t.json", cfg)
    assert len(calls) == 3  # đoạn đã nhận dạng được cache, không gửi lại
