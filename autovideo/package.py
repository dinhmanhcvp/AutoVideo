"""Đóng gói video để tăng CTR & thời gian xem: mốc chương từ timeline giọng đọc thật, mô tả YouTube
hoàn chỉnh (2 dòng đầu gây tò mò + mục lục + CTA + hashtag), bình luận ghim, 3 phương án tên/thumbnail."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from . import ff


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"[^\w]+", " ", text).strip()


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def main_timeline(work: Path, gap_ms: int) -> list[tuple[str, float, float]]:
    """[(text, start, dur)] của từng đoạn TTS trong main.wav (hoặc voice.wav nếu không có hook)."""
    chunks = json.loads((work / "tts" / "chunks.json").read_text(encoding="utf-8"))
    t, out = 0.0, []
    for i, text in enumerate(chunks):
        dur = ff.duration(work / "tts" / f"{i:04d}.norm.wav")
        out.append((text, t, dur))
        t += dur + gap_ms / 1000
    return out


def locate(first_words: str, timeline) -> float | None:
    """Thời điểm (trong main) của câu bắt đầu bằng first_words; nội suy theo vị trí ký tự trong đoạn."""
    key = _norm(first_words)
    if not key:
        return None
    probes = [key, " ".join(key.split()[:5]), " ".join(key.split()[:3])]
    for probe in probes:
        for text, start, dur in timeline:
            n = _norm(text)
            pos = n.find(probe)
            if pos >= 0:
                return start + dur * pos / max(1, len(n))
    return None


def chapters(meta: dict, work: Path, cfg: dict) -> list[tuple[float, str]]:
    """Mốc chương theo thời gian VIDEO. YouTube yêu cầu: bắt đầu 00:00, ≥3 mốc, mỗi mốc ≥10 giây."""
    lead = cfg["render"]["lead_in"]
    timeline = main_timeline(work, cfg["tts"]["gap_ms"])
    main_offset = lead
    marks: list[tuple[float, str]] = []
    if (work / "hook.wav").exists():
        main_offset = lead + ff.duration(work / "hook.wav") + 1.0
        marks.append((0.0, "Mở đầu"))
        marks.append((main_offset, "Bắt đầu câu chuyện"))
    else:
        marks.append((0.0, "Bắt đầu câu chuyện"))
    for ch in meta.get("chapters", [])[1:]:  # chương đầu trùng "Bắt đầu câu chuyện"
        t = locate(ch.get("first_words", ""), timeline)
        if t is not None:
            marks.append((main_offset + t, ch.get("title", "").strip() or "…"))
    marks.sort()
    cleaned: list[tuple[float, str]] = []
    for t, title in marks:
        if not cleaned or t - cleaned[-1][0] >= 10:
            cleaned.append((t, title))
    return cleaned if len(cleaned) >= 3 else []


def description(meta: dict, cfg: dict, marks: list[tuple[float, str]], topic_playlist: str | None = None) -> str:
    ch = cfg["channel"]
    parts = [meta.get("description", "").strip()]
    if marks:
        parts.append("⏱ MỤC LỤC\n" + "\n".join(f"{fmt_ts(t)} {title}" for t, title in marks))
    cta = []
    if topic_playlist:
        cta.append(f"▶ Nghe thêm truyện cùng thể loại: https://www.youtube.com/playlist?list={topic_playlist}")
    if ch.get("subscribe_url"):
        cta.append(f"🔔 Đăng ký kênh để nghe truyện mới mỗi ngày: {ch['subscribe_url']}")
    else:
        cta.append(f"🔔 Đăng ký {ch['name']} để nghe truyện mới mỗi ngày.")
    if ch.get("description_footer"):
        cta.append(ch["description_footer"].strip())
    parts.append("\n".join(cta))
    parts.append(" ".join(meta.get("hashtags", [])))  # 3 hashtag đầu hiện phía trên tiêu đề
    return "\n\n".join(p for p in parts if p)


def render_variants(bg: Path, meta: dict, work: Path, tcfg: dict) -> list[Path]:
    """thumbnail.jpg (phương án 1) + thumbnail_2/3.jpg — dùng cho YouTube "Thử nghiệm & so sánh" hoặc
    chọn trên điện thoại. Phương án 2/3 đổi tên truyện và lật bên ảnh để khác biệt rõ."""
    from .thumbnail import render_thumbnail

    outs = []
    for i, v in enumerate(meta.get("title_variants") or [{"story_title": meta.get("story_title", ""),
                                                           "thumb_highlight": meta.get("thumb_highlight", [])}]):
        out = work / ("thumbnail.jpg" if i == 0 else f"thumbnail_{i + 1}.jpg")
        if not out.exists():
            vcfg = dict(tcfg)
            if i == 2:
                vcfg["image_side"] = "right" if tcfg.get("image_side", "left") == "left" else "left"
            render_thumbnail(bg, {**meta, "story_title": v["story_title"], "thumb_highlight": v["thumb_highlight"]},
                             out, vcfg)
        outs.append(out)
    return outs
