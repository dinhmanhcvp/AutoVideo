"""Test luồng duyệt qua Telegram + upload YouTube với client giả lập (không gọi mạng)."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from autovideo import ff, review, youtube
from autovideo.config import load_config


class FakeTG:
    chat_id = "42"

    def __init__(self):
        self.sent = []
        self.n = 0

    def _msg(self, kind, **kw):
        self.n += 1
        self.sent.append((kind, kw))
        return {"message_id": self.n}

    def text(self, text, buttons=None, chat_id=None, **kw):
        return self._msg("text", text=text, buttons=buttons)

    def photo(self, path, caption="", buttons=None):
        return self._msg("photo", path=path, caption=caption)

    def video(self, path, caption="", buttons=None):
        assert Path(path).stat().st_size < 50 * 1024 * 1024
        return self._msg("video", path=path)

    def call(self, method, files=None, **kw):
        return self._msg(method, files=files)

    def edit_buttons(self, message_id, buttons=None):
        return self._msg("edit", message_id=message_id)

    def answer(self, cid, text=""):
        return self._msg("answer", text=text)

    def texts(self):
        return [kw["text"] for k, kw in self.sent if k == "text"]


class FakeYT:
    uploads = []

    @staticmethod
    def service(cfg):
        return "svc"

    @staticmethod
    def upload(yt, video, thumb, meta, cfg, publish_at=None):
        FakeYT.uploads.append((meta, publish_at))
        return f"VID{len(FakeYT.uploads)}"

    next_slot = staticmethod(youtube.next_slot)


@pytest.fixture
def ready(tmp_path):
    dest = tmp_path / "ready" / "2026-11-24_chuyen-tinh"
    dest.mkdir(parents=True)
    ff.run(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=15", "-f", "lavfi", "-i", "sine=frequency=400",
            "-t", 60, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", dest / "video.mp4"])
    from PIL import Image
    Image.new("RGB", (1280, 720), "navy").save(dest / "thumbnail.jpg")
    (dest / "title.txt").write_text("Chuyện Tình Đêm Mưa", encoding="utf-8")
    (dest / "description.txt").write_text("Mô tả", encoding="utf-8")
    (dest / "tags.txt").write_text("truyện audio, tâm sự", encoding="utf-8")
    (dest / "script_vi.txt").write_text("Xin chào...", encoding="utf-8")
    cfg = load_config(overrides={"review": {"enabled": True, "state_file": str(tmp_path / "reviews.json")},
                                 "youtube": {"enabled": True}, "workdir": str(tmp_path / "out")})
    return dest, cfg


def test_preview_is_head_plus_middle(ready, tmp_path):
    dest, _ = ready
    out = review.make_preview(dest / "video.mp4", tmp_path / "p.mp4", head=20, middle=10)
    assert abs(ff.duration(out) - 30) < 1


def test_notify_sends_everything_with_buttons(ready):
    dest, cfg = ready
    tg = FakeTG()
    rid = review.notify(dest, cfg, "tam_su", tg)
    kinds = [k for k, _ in tg.sent]
    assert kinds == ["photo", "video", "sendDocument", "text"]
    buttons = tg.sent[-1][1]["buttons"]
    assert ("✅ Đăng ngay", f"pub:{rid}") in buttons[0]
    assert review.reviews_store(cfg).get(rid)["status"] == "pending"


def test_publish_now_schedule_and_title_edit(ready, monkeypatch):
    dest, cfg = ready
    tg = FakeTG()
    rid = review.notify(dest, cfg, "tam_su", tg)
    bot = review.Bot(cfg, None, tg=tg, yt_module=FakeYT)
    monkeypatch.setattr(bot, "_bg", lambda fn, *a: fn(*a))  # chạy đồng bộ trong test

    # Sửa tiêu đề từ điện thoại
    bot.handle({"callback_query": {"id": "c1", "data": f"ttl:{rid}", "message": {"chat": {"id": 42}}}})
    bot.handle({"message": {"chat": {"id": 42}, "text": "Tiêu Đề Mới Hay Hơn"}})
    assert (dest / "title.txt").read_text(encoding="utf-8") == "Tiêu Đề Mới Hay Hơn"

    # Người lạ bấm nút => bỏ qua
    bot.handle({"callback_query": {"id": "c2", "data": f"pub:{rid}", "message": {"chat": {"id": 999}}}})
    assert FakeYT.uploads == []

    bot.handle({"callback_query": {"id": "c3", "data": f"sch:{rid}", "message": {"chat": {"id": 42}}}})
    meta, when = FakeYT.uploads[-1]
    assert meta["youtube_title"] == "Tiêu Đề Mới Hay Hơn" and meta["tags"] == ["truyện audio", "tâm sự"]
    assert when is not None and when.strftime("%H:%M") in cfg["youtube"]["schedule_slots"]
    rec = review.reviews_store(cfg).get(rid)
    assert rec["status"] == "scheduled" and rec["youtube_id"] == "VID1"

    # Bấm lại lần nữa không upload trùng
    bot.handle({"callback_query": {"id": "c4", "data": f"pub:{rid}", "message": {"chat": {"id": 42}}}})
    assert len(FakeYT.uploads) == 1


def test_reject_moves_folder(ready):
    dest, cfg = ready
    tg = FakeTG()
    rid = review.notify(dest, cfg, "t", tg)
    review.Bot(cfg, None, tg=tg).handle(
        {"callback_query": {"id": "c", "data": f"del:{rid}", "message": {"chat": {"id": 42}}}})
    assert not dest.exists() and (dest.parent / "_rejected" / dest.name).exists()


def test_next_slot_skips_taken_and_past():
    tz = "Asia/Ho_Chi_Minh"
    now = datetime(2026, 11, 24, 20, 0, tzinfo=ZoneInfo(tz))
    s1 = youtube.next_slot(["19:30", "21:30"], tz, [], now)
    assert s1 == datetime(2026, 11, 24, 21, 30, tzinfo=ZoneInfo(tz))
    s2 = youtube.next_slot(["19:30", "21:30"], tz, [s1.isoformat()], now)
    assert s2 == datetime(2026, 11, 25, 19, 30, tzinfo=ZoneInfo(tz))


def test_daily_run_catches_up_once(ready, monkeypatch):
    _, cfg = ready
    bot = review.Bot(cfg, None, tg=FakeTG())
    started = []
    monkeypatch.setattr(bot, "start_auto", lambda topics=None: started.append(1) or True)
    bot.daily_tick(datetime(2026, 11, 24, 1, 59))
    bot.daily_tick(datetime(2026, 11, 24, 9, 0))   # PC bật muộn => chạy bù
    bot.daily_tick(datetime(2026, 11, 24, 9, 1))   # không chạy lại trong ngày
    bot.daily_tick(datetime(2026, 11, 25, 2, 0))
    assert len(started) == 2
