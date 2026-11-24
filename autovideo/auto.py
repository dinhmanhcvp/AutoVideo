"""Chế độ tự động: chủ đề -> tìm truyện mới trên nhiều nguồn -> pipeline -> thư mục ready/ để đăng."""
from __future__ import annotations

import json
import re
import shutil
import time
import traceback
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import _deep_merge
from .pipeline import STAGES, Job, slugify

TOPIC_ONLY_KEYS = {"name", "label", "keywords", "sites", "min_minutes", "max_minutes", "enabled"}


def topic_config(cfg: dict, topic: dict) -> dict:
    """Config của 1 chủ đề = config chung đè bởi các khóa trong topic (genre, tts, render...)."""
    tcfg = _deep_merge(cfg, {k: v for k, v in topic.items() if k not in TOPIC_ONLY_KEYS})
    tcfg["_topic"] = topic["name"]
    return tcfg


def inbox_candidates(cfg: dict, topic_name: str, default_topic: str | None) -> list[dict]:
    """Truyện bạn tự tuyển (file .txt tiếng Trung hoặc tiếng Việt) được ưu tiên làm trước:
    inbox/<tên_chủ_đề>/*.txt, hoặc inbox/*.txt cho chủ đề mặc định."""
    inbox = Path(cfg["auto"].get("inbox_dir", "inbox"))
    files = sorted((inbox / topic_name).glob("*.txt")) if (inbox / topic_name).exists() else []
    if topic_name == default_topic and inbox.exists():
        files += sorted(inbox.glob("*.txt"))
    return [{"url": str(f.resolve()), "title": f.stem, "inbox": True} for f in files]


def canonical_key(url: str) -> str:
    """Bilibili BVxxxx / YouTube v=... / URL không query — để nhận ra cùng một video."""
    u = urlparse(url)
    bv = re.search(r"(BV[0-9A-Za-z]{10})", url)
    if bv:
        return f"bilibili:{bv.group(1)}"
    if "youtube.com" in u.netloc or "youtu.be" in u.netloc:
        vid = parse_qs(u.query).get("v", [u.path.strip("/").split("/")[-1]])[0]
        return f"youtube:{vid}"
    return f"{u.netloc}{u.path}".rstrip("/")


def title_key(title: str) -> str:
    """Dấu vân tay tiêu đề — bắt truyện bị re-up trùng giữa Bilibili và YouTube."""
    t = unicodedata.normalize("NFKC", title or "").lower()
    t = re.sub(r"【.*?】|\[.*?\]|（.*?）|\(.*?\)", "", t)  # bỏ tag kiểu 【有声书】
    t = re.sub(r"[\W_]+", "", t)
    return t[:40]


class History:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def should_skip(self, cand: dict, max_attempts: int) -> str | None:
        rec = self.data.get(canonical_key(cand["url"]))
        if rec:
            if rec["status"] in ("done", "skipped"):
                return rec["status"]
            if rec.get("attempts", 0) >= max_attempts:
                return "quá số lần lỗi"
        tk = title_key(cand.get("title", ""))
        if tk and len(tk) >= 6:
            for r in self.data.values():
                if r.get("title_key") == tk and r["status"] == "done":
                    return "trùng tiêu đề"
        return None

    def mark(self, cand: dict, status: str, topic: str, **extra):
        key = canonical_key(cand["url"])
        rec = self.data.setdefault(key, {"attempts": 0})
        rec.update(url=cand["url"], title=cand.get("title", ""), title_key=title_key(cand.get("title", "")),
                   topic=topic, status=status, updated=time.strftime("%Y-%m-%d %H:%M"), **extra)
        if status == "failed":
            rec["attempts"] = rec.get("attempts", 0) + 1
        self._save()


def duration_ok(seconds, topic: dict) -> bool:
    if seconds is None:
        return True  # nguồn không báo độ dài — kiểm tra lại sau khi tải
    minutes = seconds / 60
    return topic.get("min_minutes", 0) <= minutes <= topic.get("max_minutes", 10**6)


def discover(topic: dict, want: int, search_fn=None) -> list[dict]:
    """Tìm ứng viên trên mọi (từ khóa × nguồn), xen kẽ các nguồn, lọc độ dài, bỏ trùng."""
    if search_fn is None:
        from .fetch import search as search_fn
    per_query = max(5, want * 4)
    buckets: list[list[dict]] = []
    for kw in topic["keywords"]:
        for site in topic.get("sites", ["bilisearch"]):
            try:
                found = search_fn(kw, site, per_query)
            except Exception as e:  # 1 nguồn lỗi không chặn nguồn khác
                print(f"  [tìm] lỗi {site} '{kw}': {e}")
                continue
            buckets.append([r for r in found if duration_ok(r.get("duration"), topic)])
    seen, out = set(), []
    for i in range(max((len(b) for b in buckets), default=0)):  # round-robin giữa các nguồn
        for b in buckets:
            if i < len(b) and (k := canonical_key(b[i]["url"])) not in seen:
                seen.add(k)
                out.append(b[i])
    return out


def export(job: Job, ready_dir: Path) -> Path:
    meta = json.loads(job.p("metadata.json").read_text(encoding="utf-8"))
    dest = ready_dir / f"{date.today().isoformat()}_{slugify(meta.get('youtube_title', ''), 60) or job.dir.name}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("video.mp4", "thumbnail.jpg", "thumbnail_2.jpg", "thumbnail_3.jpg", "tiktok.mp4", "short.mp4",
                 "tiktok_caption.txt", "pinned_comment.txt", "script_vi.txt", "source_info.json", "cost.json"):
        if job.p(name).exists():
            shutil.copy(job.p(name), dest / name)
    (dest / "title.txt").write_text(meta.get("youtube_title", ""), encoding="utf-8")
    (dest / "titles.json").write_text(json.dumps(meta.get("titles", []), ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    (dest / "description.txt").write_text(job.p("youtube_description.txt").read_text(encoding="utf-8"),
                                          encoding="utf-8")
    (dest / "tags.txt").write_text(", ".join(meta.get("tags", [])), encoding="utf-8")
    analysis = job.read_json("analysis.json")
    if analysis:
        (dest / "analysis.json").write_text(json.dumps(
            {k: analysis.get(k) for k in ("score", "scores", "logline_vi", "complete", "red_flags")},
            ensure_ascii=False, indent=1), encoding="utf-8")
    return dest


def _notify(tg, text: str):
    if tg:
        try:
            tg.text(text)
        except Exception:
            pass


def run_auto(cfg: dict, topics: list[str] | None = None, per_topic: int | None = None,
             dry_run: bool = False, search_fn=None) -> list[Path]:
    from .analyze import StoryRejected
    from .analytics import plan_quotas

    acfg = cfg["auto"]
    history = History(Path(acfg["history_file"]))
    tg = None
    if cfg.get("review", {}).get("enabled") and not dry_run:
        from .telegram import Telegram

        tg = Telegram(cfg["review"].get("bot_token"), cfg["review"].get("chat_id"))
    ready = Path(acfg["ready_dir"])
    produced: list[Path] = []
    rejected: list[str] = []

    all_topics = cfg.get("topics") or []
    if topics:  # gọi đích danh: chạy cả chủ đề đang tắt
        active = [t for t in all_topics if t["name"] in topics]
    else:
        active = [t for t in all_topics if t.get("enabled", True) is not False]
    quotas = plan_quotas(cfg, active, per_topic)
    default_topic = acfg.get("inbox_topic") or (active[0]["name"] if active else None)

    for topic in active:
        name = topic["name"]
        need = quotas.get(name, 0)
        if need <= 0:
            continue
        tcfg = topic_config(cfg, topic)
        print(f"=== Chủ đề: {name} (cần {need}) ===")
        made, tried = 0, 0
        max_tries = acfg.get("max_candidates_per_video", 5) * need
        inbox = inbox_candidates(cfg, name, default_topic)
        candidates = inbox + (discover(topic, need, search_fn) if len(inbox) < need else [])
        for cand in candidates:
            if made >= need or tried >= max_tries:
                break
            if history.should_skip(cand, acfg.get("max_attempts", 2)):
                continue
            print(f"→ {cand.get('title', '')[:60]}  [{cand['url']}]")
            if dry_run:
                made += 1
                continue
            tried += 1
            job = Job(cand["url"], tcfg, strict=not cand.get("inbox"))  # truyện bạn tự chọn: không loại
            try:
                job.run(["fetch"])
                info_file = job.p("source_info.json")
                if info_file.exists():
                    dur = json.loads(info_file.read_text(encoding="utf-8")).get("duration")
                    if not duration_ok(dur, topic):
                        history.mark(cand, "skipped", name, reason="độ dài không hợp")
                        continue
                job.run([s for s in STAGES if s != "fetch"])
                dest = export(job, ready)
                history.mark(cand, "done", name, output=str(dest))
                if cand.get("inbox"):
                    done_dir = Path(acfg.get("inbox_dir", "inbox")) / "_done"
                    done_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(cand["url"], done_dir / Path(cand["url"]).name)
                produced.append(dest)
                made += 1
                print(f"✔ Sẵn sàng đăng: {dest}")
                if tg:
                    try:
                        from .review import notify

                        notify(dest, cfg, name, tg)
                    except Exception as e:  # lỗi gửi Telegram không làm hỏng video đã xong
                        traceback.print_exc()
                        print(f"  [review] gửi Telegram lỗi: {e}")
            except StoryRejected as e:
                print(f"  ✗ Bỏ qua: {e}")
                history.mark(cand, "skipped", name, reason=str(e)[:200])
                rejected.append(f"{cand.get('title', '')[:40]} — {e}")
            except Exception as e:
                traceback.print_exc()
                history.mark(cand, "failed", name, error=str(e)[:300])
                _notify(tg, f"⚠️ Lỗi khi làm truyện:\n{cand.get('title', '')}\n{str(e)[:300]}")
        if made < need:
            print(f"  [!] Chủ đề {name}: chỉ có {made}/{need} truyện đạt chuẩn — thêm từ khóa/nguồn hoặc thả truyện vào inbox/.")
    if tg:
        msg = f"🏁 Xong lượt chạy: {len(produced)} video mới chờ duyệt."
        if rejected:
            msg += f"\n🚫 Loại {len(rejected)} truyện không đạt chuẩn:\n" + "\n".join(rejected[:8])
        _notify(tg, msg)
    return produced
