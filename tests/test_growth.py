import json
from pathlib import Path

from PIL import Image

from autovideo import analytics, review
from autovideo.config import load_config


def cfg_with(tmp_path, **auto):
    return load_config(overrides={"workdir": str(tmp_path), "auto": auto,
                                  "review": {"state_file": str(tmp_path / "reviews.json")}})


TOPICS = [{"name": "a"}, {"name": "b"}, {"name": "c"}]


def write_stats(tmp_path, data):
    (tmp_path / "analytics.json").write_text(json.dumps(data), encoding="utf-8")


def rec(topic, views, age, title="t", pct=None):
    return {"topic": topic, "views": views, "age_days": age, "privacy": "public", "title": title,
            "published": f"2026-11-{int(30 - age):02d}T00:00:00Z", "avg_view_percent": pct}


def test_quotas_fixed_when_not_adaptive(tmp_path):
    assert analytics.plan_quotas(cfg_with(tmp_path, per_topic=2), TOPICS) == {"a": 2, "b": 2, "c": 2}
    assert analytics.plan_quotas(cfg_with(tmp_path), TOPICS, per_topic=1) == {"a": 1, "b": 1, "c": 1}


def test_adaptive_quotas_favor_winner_but_explore_new(tmp_path):
    cfg = cfg_with(tmp_path, adaptive=True, daily_total=6)
    write_stats(tmp_path, {"v1": rec("a", 9000, 3), "v2": rec("a", 6000, 3), "v3": rec("b", 300, 3),
                           "young": rec("b", 99999, 1)})  # < 2 ngày: chưa tính
    q = analytics.plan_quotas(cfg, TOPICS)
    assert sum(q.values()) == 6
    assert q["a"] > q["b"] and q["c"] >= 1  # c chưa có dữ liệu => vẫn được thử


def test_report_text_mentions_best_topic_and_low_retention(tmp_path):
    stats = {"v1": rec("a", 5000, 5, "Hay", 45), "v2": rec("b", 200, 5, "Dở", 18)}
    text = analytics.report_text(cfg_with(tmp_path), stats)
    assert "Chủ đề hiệu quả nhất: a" in text and "giữ chân < 25%" in text and "5.200 lượt xem" in text


class FakeYT:
    def __init__(self):
        self.uploads, self.playlist = [], []

    def service(self, cfg):
        return "svc"

    def upload(self, yt, video, thumb, meta, cfg, publish_at=None):
        self.uploads.append((Path(video).name, meta))
        return f"ID{len(self.uploads)}"

    def add_to_playlist(self, yt, pl, vid):
        self.playlist.append((pl, vid))

    from autovideo.youtube import next_slot as _ns
    next_slot = staticmethod(_ns)


class TG:
    chat_id = "1"

    def __init__(self):
        self.texts = []

    def text(self, t, buttons=None, **k):
        self.texts.append(t)
        return {"message_id": 1}

    def edit_buttons(self, *a, **k):
        pass


def ready_folder(tmp_path):
    dest = tmp_path / "ready" / "x"
    dest.mkdir(parents=True)
    for n in (1, 2, 3):
        Image.new("RGB", (64, 36), ["red", "green", "blue"][n - 1]).save(dest / f"thumbnail{'' if n == 1 else f'_{n}'}.jpg")
    for name in ("video.mp4", "short.mp4"):
        (dest / name).write_bytes(b"x")
    (dest / "title.txt").write_text("T1", encoding="utf-8")
    (dest / "titles.json").write_text(json.dumps(["T1", "T2", "T3"]), encoding="utf-8")
    (dest / "description.txt").write_text("mô tả", encoding="utf-8")
    (dest / "tags.txt").write_text("a, b", encoding="utf-8")
    (dest / "pinned_comment.txt").write_text("Bạn chọn ai?", encoding="utf-8")
    return dest


def test_select_variant_then_publish_with_shorts_and_playlist(tmp_path):
    cfg = load_config(overrides={"review": {"state_file": str(tmp_path / "r.json")},
                                 "youtube": {"enabled": True, "playlists": {"tam_su": "PL1"}}})
    dest = ready_folder(tmp_path)
    review.reviews_store(cfg).update("r1", dest=str(dest), title="T1", topic="tam_su", status="pending", message_id=1)
    tg, yt = TG(), FakeYT()
    review.do_select_variant("r1", 3, cfg, tg)
    assert (dest / "title.txt").read_text(encoding="utf-8") == "T3"
    assert Image.open(dest / "thumbnail.jpg").getpixel((5, 5))[2] > 200  # thumbnail xanh = phương án 3
    review.do_publish("r1", cfg, tg, False, yt_module=yt)
    assert [u[0] for u in yt.uploads] == ["video.mp4", "short.mp4"]
    assert yt.uploads[0][1]["youtube_title"] == "T3"
    assert "https://youtu.be/ID1" in yt.uploads[1][1]["description_full"]
    assert yt.uploads[1][1]["youtube_title"].endswith("#shorts")
    assert yt.playlist == [("PL1", "ID1")]
    assert any("Bạn chọn ai?" in t for t in tg.texts)
    assert review.reviews_store(cfg).get("r1")["shorts_id"] == "ID2"


def test_fetch_stats_with_fake_clients(tmp_path):
    cfg = cfg_with(tmp_path)
    review.reviews_store(cfg).update("r1", youtube_id="V1", topic="a", status="published", title="x")

    class Req:
        def __init__(self, data):
            self.data = data

        def execute(self):
            return self.data

    class Videos:
        def list(self, **kw):
            assert kw["id"] == "V1"
            return Req({"items": [{"id": "V1", "statistics": {"viewCount": "1200", "likeCount": "30"},
                                   "snippet": {"title": "Tên", "publishedAt": "2026-11-01T00:00:00Z"},
                                   "status": {"privacyStatus": "public"}}]})

    class YT:
        def videos(self):
            return Videos()

    class Reports:
        def query(self, **kw):
            return Req({"rows": [["V1", 1200, 600, 41.5]]})

    class YTA:
        def reports(self):
            return Reports()

    stats = analytics.fetch_stats(cfg, YT(), YTA())
    assert stats["V1"]["views"] == 1200 and stats["V1"]["avg_view_percent"] == 41.5
    assert stats["V1"]["topic"] == "a" and stats["V1"]["age_days"] > 2
