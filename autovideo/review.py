"""Duyệt video qua điện thoại bằng bot Telegram.

Luồng: auto làm xong 1 video -> bot gửi thumbnail + tiêu đề + clip xem thử + toàn văn bản dịch
-> bạn bấm nút trên điện thoại: Đăng ngay / Hẹn giờ / Sửa tiêu đề / Bỏ -> PC tự upload YouTube.
Chạy bot thường trực:  python -m autovideo bot -c config.yaml
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import ff
from .telegram import Telegram

_lock = threading.RLock()


# ------------------------------------------------------------------ lưu trạng thái

class Reviews:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        with _lock:
            return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def update(self, rid: str, **fields) -> dict:
        with _lock:
            data = self.load()
            data.setdefault(rid, {}).update(fields)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            return data[rid]

    def get(self, rid: str) -> dict | None:
        return self.load().get(rid)


def reviews_store(cfg: dict) -> Reviews:
    return Reviews(Path(cfg["review"]["state_file"]))


# ------------------------------------------------------------------ gửi bản duyệt

def make_preview(video: Path, out: Path, head: float = 120, middle: float = 45) -> Path:
    """Clip xem thử nhẹ (480p, ~10–15 MB, dưới giới hạn 50 MB của bot): đầu video (lời dẫn + mở truyện)
    + một đoạn giữa video (kiểm tra nhạc nền/giọng/hình ở phần sau)."""
    total = ff.duration(video)
    vf = "scale=-2:480,fps=24,format=yuv420p"
    common = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "64k",
              "-movflags", "+faststart"]
    if head <= 0:  # chỉ lấy 1 đoạn giữa video
        ff.run(["-ss", f"{max(0.0, total / 2 - middle / 2):.1f}", "-t", middle, "-i", video, "-vf", vf, *common, out])
        return out
    if total <= head + middle + 10:
        ff.run(["-i", video, "-t", head + middle, "-vf", vf, *common, out])
        return out
    mid = total / 2
    graph = (f"[0:v]{vf}[v0];[1:v]{vf}[v1];[0:a]aresample=44100[a0];[1:a]aresample=44100[a1];"
             "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    ff.run(["-t", head, "-i", video, "-ss", f"{mid:.1f}", "-t", middle, "-i", video,
            "-filter_complex", graph, "-map", "[v]", "-map", "[a]", *common, out])
    return out


def review_id(dest: Path) -> str:
    return hashlib.sha1(str(dest.resolve()).encode()).hexdigest()[:10]


def buttons_for(rid: str, cfg: dict):
    if cfg.get("youtube", {}).get("enabled"):
        return [[("✅ Đăng ngay", f"pub:{rid}"), ("🕒 Hẹn giờ", f"sch:{rid}")],
                [("✏️ Sửa tiêu đề", f"ttl:{rid}"), ("🗑 Bỏ", f"del:{rid}")]]
    return [[("✅ Duyệt", f"ok:{rid}"), ("✏️ Sửa tiêu đề", f"ttl:{rid}")], [("🗑 Bỏ", f"del:{rid}")]]


def fmt_dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def notify(dest: Path, cfg: dict, topic: str = "", tg: Telegram | None = None) -> str:
    """Gửi 1 video sang điện thoại để duyệt. Trả về review id."""
    rcfg = cfg["review"]
    tg = tg or Telegram(rcfg.get("bot_token"), rcfg.get("chat_id"))
    rid = review_id(dest)
    title = (dest / "title.txt").read_text(encoding="utf-8")
    video = dest / "video.mp4"
    duration = ff.duration(video)
    source = ""
    if (dest / "source_info.json").exists():
        info = json.loads((dest / "source_info.json").read_text(encoding="utf-8"))
        source = f"\nNguồn: {info.get('title') or ''} {info.get('webpage_url') or ''}"

    analysis = json.loads((dest / "analysis.json").read_text(encoding="utf-8")) if (dest / "analysis.json").exists() else {}
    score = f" · Điểm truyện {analysis['score']}/10" if analysis.get("score") else ""
    tg.photo(dest / "thumbnail.jpg", caption=f"🎬 {title}\nChủ đề: {topic} · Dài {fmt_dur(duration)}{score}{source}"
                                             + (f"\n💬 {analysis['logline_vi']}" if analysis.get("logline_vi") else ""))
    titles = json.loads((dest / "titles.json").read_text(encoding="utf-8")) if (dest / "titles.json").exists() else []
    for n in (2, 3):  # các phương án tên/thumbnail khác — bấm để chọn
        alt = dest / f"thumbnail_{n}.jpg"
        if alt.exists() and len(titles) >= n:
            tg.photo(alt, caption=f"Phương án {n}: {titles[n - 1]}", buttons=[[(f"👉 Chọn phương án {n}", f"var:{rid}:{n}")]])
    tiktok = dest / "tiktok.mp4"
    preview = dest / "preview.mp4"
    if tiktok.exists():
        # Hook = phần mở đầu video YouTube, nên clip TikTok vừa để duyệt hook vừa để lưu về máy đăng luôn
        tg.video(tiktok, caption=f"📱 Clip TikTok (hook {fmt_dur(ff.duration(tiktok))}) — giữ để lưu về máy và đăng")
        cap = dest / "tiktok_caption.txt"
        if cap.exists() and cap.read_text(encoding="utf-8").strip():
            tg.text(cap.read_text(encoding="utf-8"))  # tin riêng để chạm-giữ sao chép caption
        if not preview.exists():
            make_preview(video, preview, 0, rcfg.get("preview_middle", 45))
        tg.video(preview, caption="▶️ Xem thử 1 đoạn giữa video YouTube (giọng, nhạc nền, hình)")
    else:
        if not preview.exists():
            make_preview(video, preview, rcfg.get("preview_head", 120), rcfg.get("preview_middle", 45))
        tg.video(preview, caption="▶️ Xem thử: phần mở đầu + 1 đoạn giữa video")
    script = dest / "script_vi.txt"
    if script.exists():
        tg.call("sendDocument", files={"document": script}, chat_id=tg.chat_id,
                caption="📄 Toàn văn bản dịch (mở trên điện thoại để đọc)")
    desc = (dest / "description.txt").read_text(encoding="utf-8")
    tags = (dest / "tags.txt").read_text(encoding="utf-8")
    pinned = dest / "pinned_comment.txt"
    if pinned.exists() and pinned.read_text(encoding="utf-8").strip():
        desc += "\n\n📌 BÌNH LUẬN GHIM (dán và ghim sau khi đăng):\n" + pinned.read_text(encoding="utf-8").strip()
    msg = tg.text(f"📝 TIÊU ĐỀ:\n{title}\n\n📄 MÔ TẢ:\n{desc}\n\n🏷 TAG: {tags}\n\n👉 Chọn thao tác:",
                  buttons=buttons_for(rid, cfg))
    reviews_store(cfg).update(rid, dest=str(dest), title=title, topic=topic, status="pending",
                              message_id=msg["message_id"], created=datetime.now().isoformat(timespec="minutes"))
    return rid


# ------------------------------------------------------------------ xử lý nút bấm

def _yt_meta(dest: Path) -> dict:
    return {
        "youtube_title": (dest / "title.txt").read_text(encoding="utf-8").strip(),
        "description_full": (dest / "description.txt").read_text(encoding="utf-8"),
        "tags": [t.strip() for t in (dest / "tags.txt").read_text(encoding="utf-8").split(",") if t.strip()],
    }


def do_publish(rid: str, cfg: dict, tg: Telegram, schedule: bool, yt_module=None, yt_service=None):
    from . import youtube as default_yt

    yt_mod = yt_module or default_yt
    store = reviews_store(cfg)
    rec = store.get(rid)
    if not rec or rec["status"] not in ("pending", "failed"):
        tg.text(f"Video này đã ở trạng thái: {rec and rec['status']}")
        return
    ycfg = cfg["youtube"]
    dest = Path(rec["dest"])
    publish_at = None
    if schedule:
        taken = [r["publish_at"] for r in store.load().values() if r.get("publish_at") and r["status"] == "scheduled"]
        publish_at = yt_mod.next_slot(ycfg["schedule_slots"], ycfg["timezone"], taken)
    store.update(rid, status="uploading")
    tg.edit_buttons(rec["message_id"], None)
    tg.text(f"⏫ Đang upload: {rec['title']}")
    try:
        yt = yt_service or yt_mod.service(ycfg)
        vid = yt_mod.upload(yt, dest / "video.mp4", dest / "thumbnail.jpg", _yt_meta(dest), ycfg, publish_at)
    except Exception as e:
        traceback.print_exc()
        store.update(rid, status="failed", error=str(e)[:300])
        tg.text(f"❌ Upload lỗi: {e}", buttons=buttons_for(rid, cfg))
        return
    url = f"https://youtu.be/{vid}"
    if publish_at:
        store.update(rid, status="scheduled", youtube_id=vid, publish_at=publish_at.isoformat())
        tg.text(f"🕒 Đã hẹn đăng lúc {publish_at:%H:%M %d/%m}\n{url}")
    else:
        store.update(rid, status="published", youtube_id=vid)
        tg.text(f"✅ Đã đăng công khai\n{url}")
    playlist = (ycfg.get("playlists") or {}).get(rec.get("topic", ""))
    if playlist:
        try:
            yt_mod.add_to_playlist(yt, playlist, vid)
        except Exception as e:
            tg.text(f"⚠️ Không thêm được vào playlist: {e}")
    short = dest / "short.mp4"
    if cfg.get("shorts", {}).get("upload") and short.exists():
        try:
            meta = _yt_meta(dest)
            story = meta["youtube_title"]
            sm = {"youtube_title": f"{cfg['shorts'].get('title_prefix', '')}{story}"[:90] + " #shorts",
                  "description_full": f"▶ Nghe trọn bộ: {url}\n\n" + meta["description_full"][-400:],
                  "tags": meta["tags"]}
            sid = yt_mod.upload(yt, short, dest / "thumbnail.jpg", sm, ycfg, publish_at)
            store.update(rid, shorts_id=sid)
            tg.text(f"📱 Đã đăng Shorts: https://youtube.com/shorts/{sid}\n"
                    "Mẹo: trong YouTube Studio → Shorts → \"Video liên quan\" chọn video dài để người xem bấm sang.")
        except Exception as e:
            tg.text(f"⚠️ Upload Shorts lỗi: {e}")
    pinned = dest / "pinned_comment.txt"
    if pinned.exists() and pinned.read_text(encoding="utf-8").strip():
        tg.text("📌 Dán bình luận này dưới video rồi ghim lại:\n\n" + pinned.read_text(encoding="utf-8").strip())


def do_select_variant(rid: str, n: int, cfg: dict, tg: Telegram):
    """Đổi sang phương án tên + thumbnail số n (giữ lại bản gốc ở thumbnail_1.jpg)."""
    rec = reviews_store(cfg).get(rid)
    dest = Path(rec["dest"])
    titles = json.loads((dest / "titles.json").read_text(encoding="utf-8"))
    if not (dest / "thumbnail_1.jpg").exists():
        shutil.copy(dest / "thumbnail.jpg", dest / "thumbnail_1.jpg")
    shutil.copy(dest / f"thumbnail_{n}.jpg", dest / "thumbnail.jpg")
    (dest / "title.txt").write_text(titles[n - 1], encoding="utf-8")
    reviews_store(cfg).update(rid, title=titles[n - 1], variant=n)
    tg.text(f"✅ Đã chọn phương án {n}:\n{titles[n - 1]}", buttons=buttons_for(rid, cfg))


def do_approve_local(rid: str, cfg: dict, tg: Telegram):
    rec = reviews_store(cfg).get(rid)
    dest = Path(rec["dest"])
    approved = dest.parent / "_approved"
    approved.mkdir(exist_ok=True)
    new_dest = approved / dest.name
    shutil.move(str(dest), new_dest)
    reviews_store(cfg).update(rid, status="approved", dest=str(new_dest))
    tg.edit_buttons(rec["message_id"], None)
    tg.text(f"✅ Đã duyệt. Video nằm ở {new_dest}")


def do_reject(rid: str, cfg: dict, tg: Telegram):
    rec = reviews_store(cfg).get(rid)
    dest = Path(rec["dest"])
    rejected = dest.parent / "_rejected"
    rejected.mkdir(exist_ok=True)
    if dest.exists():
        shutil.move(str(dest), rejected / dest.name)
    reviews_store(cfg).update(rid, status="rejected", dest=str(rejected / dest.name))
    tg.edit_buttons(rec["message_id"], None)
    tg.text("🗑 Đã bỏ video này (chuyển vào ready/_rejected, có thể xóa sau).")


class Bot:
    def __init__(self, cfg: dict, config_path: str | None, tg: Telegram | None = None, yt_module=None):
        self.cfg = cfg
        self.yt_module = yt_module
        self.config_path = config_path
        rcfg = cfg["review"]
        self.tg = tg or Telegram(rcfg.get("bot_token"), rcfg.get("chat_id"))
        self.awaiting_title: str | None = None
        self.run_proc: subprocess.Popen | None = None
        self.offset_file = Path(rcfg["state_file"]).with_suffix(".offset")
        self.last_daily = None

    # -- tiện ích
    def _bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def start_auto(self, topics: list[str] | None = None) -> bool:
        if self.run_proc and self.run_proc.poll() is None:
            return False
        cmd = [sys.executable, "-m", "autovideo", "auto"]
        if self.config_path:
            cmd += ["-c", self.config_path]
        for t in topics or []:
            cmd += ["--topic", t]
        log = open(Path(self.cfg["workdir"]) / "auto_from_bot.log", "a", encoding="utf-8")
        self.run_proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        return True

    # -- xử lý
    def handle(self, update: dict):
        if cq := update.get("callback_query"):
            if str(cq["message"]["chat"]["id"]) != self.tg.chat_id:
                return  # chỉ chủ kênh được bấm
            action, _, rest = cq["data"].partition(":")
            rid, _, arg = rest.partition(":")
            self.tg.answer(cq["id"], "Đang xử lý…")
            if action == "var":
                do_select_variant(rid, int(arg), self.cfg, self.tg)
            elif action == "pub":
                self._bg(do_publish, rid, self.cfg, self.tg, False, self.yt_module)
            elif action == "sch":
                self._bg(do_publish, rid, self.cfg, self.tg, True, self.yt_module)
            elif action == "ok":
                do_approve_local(rid, self.cfg, self.tg)
            elif action == "del":
                do_reject(rid, self.cfg, self.tg)
            elif action == "ttl":
                self.awaiting_title = rid
                self.tg.text("✏️ Gửi tiêu đề mới (tối đa 100 ký tự):")
            return

        msg = update.get("message") or {}
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if text.startswith("/start") or text.startswith("/id"):
            self.tg.text(f"Chat ID của bạn: {chat_id}\nĐiền vào review.chat_id trong config.yaml.", chat_id=chat_id)
            return
        if chat_id != self.tg.chat_id:
            return
        if self.awaiting_title and text and not text.startswith("/"):
            rid, self.awaiting_title = self.awaiting_title, None
            rec = reviews_store(self.cfg).get(rid)
            new_title = text[:100]
            (Path(rec["dest"]) / "title.txt").write_text(new_title, encoding="utf-8")
            reviews_store(self.cfg).update(rid, title=new_title)
            self.tg.text(f"Đã đổi tiêu đề thành:\n{new_title}", buttons=buttons_for(rid, self.cfg))
        elif text.startswith("/run"):
            topics = text.split()[1:]
            ok = self.start_auto(topics)
            self.tg.text("▶️ Bắt đầu chạy, video xong sẽ gửi về đây." if ok else "⏳ Đang có lượt chạy khác.")
        elif text.startswith("/report"):
            self.tg.text("⏳ Đang lấy số liệu YouTube…")
            self._bg(self.send_report)
        elif text.startswith("/status"):
            data = reviews_store(self.cfg).load().values()
            count = {}
            for r in data:
                count[r["status"]] = count.get(r["status"], 0) + 1
            running = "đang chạy" if self.run_proc and self.run_proc.poll() is None else "rảnh"
            sched = sorted(r["publish_at"] for r in data if r["status"] == "scheduled")
            self.tg.text(f"Máy: {running}\nTrạng thái: {count or 'chưa có video'}\n"
                         f"Lịch đăng: {', '.join(s[:16] for s in sched) or 'trống'}")
        elif text.startswith("/pending"):
            pend = [(rid, r) for rid, r in reviews_store(self.cfg).load().items() if r["status"] in ("pending", "failed")]
            if not pend:
                self.tg.text("Không có video chờ duyệt.")
            for rid, r in pend:
                self.tg.text(f"⏳ {r['title']}", buttons=buttons_for(rid, self.cfg))
        elif text.startswith("/help") or text.startswith("/"):
            self.tg.text("/run [chủ đề] – chạy ngay\n/status – tình trạng\n/pending – video chờ duyệt\n"
                         "/report – báo cáo view, giữ chân, chủ đề hiệu quả\n/id – xem chat id")

    def send_report(self):
        from .analytics import fetch_stats, report_text

        try:
            stats = fetch_stats(self.cfg) if self.cfg.get("youtube", {}).get("enabled") else None
            self.tg.text(report_text(self.cfg, stats))
        except Exception as e:
            traceback.print_exc()
            self.tg.text(f"⚠️ Không lấy được số liệu: {e}")

    def _marker(self, kind: str) -> Path:
        return Path(self.cfg["review"]["state_file"]).with_suffix(f".{kind}")

    def daily_tick(self, now: datetime | None = None):
        now = now or datetime.now()
        rcfg = self.cfg["review"]
        at = rcfg.get("daily_run")
        if self.last_daily is None and self._marker("lastrun").exists():
            self.last_daily = self._marker("lastrun").read_text().strip()
        # Đã qua giờ hẹn hôm nay mà chưa chạy (kể cả PC mới bật sau giờ đó) => chạy bù; nhớ qua khởi động lại
        if at and now.strftime("%H:%M") >= at and self.last_daily != now.date().isoformat():
            self.last_daily = now.date().isoformat()
            self._marker("lastrun").write_text(self.last_daily)
            if self.start_auto():
                self.tg.text(f"⏰ Bắt đầu lượt chạy hằng ngày ({at}).")
        wd = rcfg.get("report_weekday")  # 0 = thứ Hai ... 6 = Chủ nhật
        if wd is not None and now.weekday() == wd and now.strftime("%H:%M") >= rcfg.get("report_time", "20:00"):
            week = now.strftime("%G-W%V")
            marker = self._marker("lastreport")
            if not marker.exists() or marker.read_text().strip() != week:
                marker.write_text(week)
                self._bg(self.send_report)

    def loop(self):
        print("Bot đang chạy. Ctrl+C để dừng.")
        offset = int(self.offset_file.read_text()) if self.offset_file.exists() else None
        while True:
            try:
                self.daily_tick()
                for upd in self.tg.updates(offset, timeout=30):
                    offset = upd["update_id"] + 1
                    self.offset_file.write_text(str(offset))
                    try:
                        self.handle(upd)
                    except Exception as e:
                        traceback.print_exc()
                        self.tg.text(f"⚠️ Lỗi: {e}")
            except KeyboardInterrupt:
                raise
            except Exception:
                traceback.print_exc()
                time.sleep(10)  # mất mạng: thử lại
