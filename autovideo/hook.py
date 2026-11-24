"""Hook 2–5 phút mở đầu video + clip TikTok dọc 9:16 để kéo người xem sang YouTube.

- make_hook: LLM chọn khoảnh khắc gay cấn nhất, viết lại thành đoạn mở màn dừng ở cao trào.
- render_tiktok: clip dọc 1080x1920 = khung tên truyện + ảnh + phụ đề cháy chữ + banner
  "Nghe trọn bộ trên YouTube" + giọng hook + lời kêu gọi + nhạc nền.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import ff
from .llm import extract_json
from .thumbnail import _font, _framed_photo, _units, cover, layout_title, mark_highlights
from .translate import fill, load_prompt


# ------------------------------------------------------------------ nội dung

def make_hook(llm, vi_text: str, meta: dict, cfg: dict) -> dict:
    hcfg = cfg["hook"]
    wpm = hcfg.get("words_per_minute", 170)
    system = fill(
        load_prompt("hook.md"),
        channel_name=cfg["channel"]["name"],
        story_title=meta.get("story_title", ""),
        min_minutes=hcfg["min_minutes"], max_minutes=hcfg["max_minutes"],
        min_words=int(hcfg["min_minutes"] * wpm), max_words=int(hcfg["max_minutes"] * wpm),
        genre_rules=load_prompt(f"genres/{cfg['genre']}.md"),
    )
    data = extract_json(llm.complete(system, "", max_tokens=16000, doc=f"<truyen>\n{vi_text}\n</truyen>"))
    if not data.get("hook"):
        raise ValueError("LLM không trả về hook")
    data.setdefault("bridge", "")
    data.setdefault("tiktok_cta", f"Nghe trọn bộ truyện {meta.get('story_title', '')} trên kênh YouTube "
                                  f"{cfg['channel']['name']} nhé.")
    data.setdefault("tiktok_caption", "")
    return data


def check_length(seconds: float, cfg: dict) -> str | None:
    lo, hi = cfg["hook"]["min_minutes"] * 60, cfg["hook"]["max_minutes"] * 60
    if seconds < lo * 0.8 or seconds > hi * 1.2:
        return f"Hook dài {seconds / 60:.1f} phút, ngoài khoảng {lo / 60:.0f}–{hi / 60:.0f} phút"
    return None


# ------------------------------------------------------------------ hình TikTok

# Vùng an toàn TikTok: đáy ~20% bị caption/tên tài khoản che, mép phải có cột nút tim/bình luận.
# => mọi nội dung nằm trong x 70..950, y < 1540.
SAFE_X0, SAFE_X1 = 70, 950
CAPTION_Y0, CAPTION_Y1 = 1100, 1390


def tiktok_frame(background: Path, meta: dict, out: Path, tcfg: dict, banner: str, badge: str) -> Path:
    """Khung tĩnh 1080x1920: nhãn + TÊN TRUYỆN + ảnh 16:9 + (chỗ trống phụ đề) + banner YouTube."""
    W, H = 1080, 1920
    cx = (SAFE_X0 + SAFE_X1) // 2
    sw = SAFE_X1 - SAFE_X0
    src = Image.open(background).convert("RGB")
    bg = cover(src, (W, H)).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), "black"), 0.55).convert("RGBA")
    d = ImageDraw.Draw(bg)

    y = 80
    if badge:
        bfont = _font(tcfg.get("badge_font") or tcfg.get("font"), 44)
        l, t, r, b = d.textbbox((0, 0), badge, font=bfont)
        bw, bh = r - l + 56, b - t + 28
        bx = cx - bw // 2
        d.rounded_rectangle((bx, y, bx + bw, y + bh), radius=bh // 2, fill=tcfg.get("badge_color", "#F6E3A1"))
        d.text((bx + 28 - l, y + 14 - t), badge, font=bfont, fill=tcfg.get("badge_text_color", "#4A2A12"))
        y += bh + 20

    words = (meta.get("story_title") or "").upper().split()
    colors = mark_highlights(words, meta.get("thumb_highlight", []), [tcfg.get("tiktok_highlight", "#FFD54F")], "#FFFFFF")
    box_h = 500 - y
    font, lines, line_h = layout_title(d, words, tcfg.get("font"), sw, box_h, 3, units=_units(words, colors, "#FFFFFF"))
    space = d.textlength(" ", font=font)
    ty = y + (box_h - line_h * len(lines)) / 2
    for line in lines:
        lw = sum(d.textlength(words[i], font=font) for i in line) + space * (len(line) - 1)
        x = cx - lw / 2
        for i in line:
            d.text((x, ty), words[i], font=font, fill=colors[i], stroke_width=5, stroke_fill="#000000")
            x += d.textlength(words[i], font=font) + space
        ty += line_h

    pw, ph = sw, round(sw * 9 / 16)
    photo = _framed_photo(src, (pw, ph), radius=36, border=9)
    bg.alpha_composite(photo, (SAFE_X0, 540))  # y 540..1035

    # Banner kêu gọi sang YouTube — ngay dưới phụ đề, trên vùng bị TikTok che
    pill_h = 110
    py = CAPTION_Y1 + 40
    d.rounded_rectangle((SAFE_X0, py, SAFE_X1, py + pill_h), radius=pill_h // 2, fill="#E53935")
    d.polygon([(SAFE_X0 + 44, py + 34), (SAFE_X0 + 44, py + pill_h - 34), (SAFE_X0 + 86, py + pill_h // 2)],
              fill="#FFFFFF")
    tx = SAFE_X0 + 110
    size = 50
    while size > 24:
        f = _font(tcfg.get("badge_font") or tcfg.get("font"), size)
        if d.textlength(banner, font=f) <= SAFE_X1 - tx - 36:
            break
        size -= 2
    l, t, r, b = d.textbbox((0, 0), banner, font=f)
    d.text((tx, py + (pill_h - (b - t)) / 2 - t), banner, font=f, fill="#FFFFFF")

    bg.convert("RGB").save(out)
    return out


def caption_image(text: str, out: Path, font_path: str | None, variation: str | None = "Bold") -> Path:
    """Phụ đề trắng viền đen, tối đa 2 dòng, căn giữa vùng phụ đề."""
    from .thumbnail import _wrap

    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    words = text.split()
    for size in range(66, 30, -3):
        f = _font(font_path, size)
        if variation:
            try:
                f.set_variation_by_name(variation)
            except Exception:
                pass
        lines = _wrap(words, f, SAFE_X1 - SAFE_X0, d)
        asc, desc = f.getmetrics()
        lh = (asc + desc) * 0.98
        if len(lines) <= 2 and lh * len(lines) <= CAPTION_Y1 - CAPTION_Y0:
            break
    y = CAPTION_Y0 + (CAPTION_Y1 - CAPTION_Y0 - lh * len(lines)) / 2
    cx = (SAFE_X0 + SAFE_X1) / 2
    for line in lines:
        s = " ".join(words[i] for i in line)
        w = d.textlength(s, font=f)
        d.text((cx - w / 2, y), s, font=f, fill="#FFFFFF", stroke_width=6, stroke_fill="#000000")
        y += lh
    img.save(out)
    return out


def caption_track(captions: list[dict], offset: float, total: float, tdir: Path, font_path, variation) -> Path:
    """Chuỗi ảnh phụ đề trong suốt + thời lượng (concat demuxer) => 1 luồng video để overlay."""
    tdir.mkdir(parents=True, exist_ok=True)
    blank = tdir / "blank.png"
    Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(blank)
    entries: list[tuple[Path, float]] = []
    t = 0.0
    for i, c in enumerate(captions):
        start, end = c["start"] + offset, c["end"] + offset
        if start > t + 0.01:
            entries.append((blank, start - t))
        entries.append((caption_image(c["text"], tdir / f"c{i:04d}.png", font_path, variation), end - start))
        t = end
    entries.append((blank, max(0.1, total - t)))
    lines = []
    for path, dur in entries:
        lines += [f"file '{path.resolve().as_posix()}'", f"duration {dur:.3f}"]
    lines.append(f"file '{entries[-1][0].resolve().as_posix()}'")  # concat demuxer cần lặp file cuối
    lst = tdir / "captions.txt"
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lst


def render_vertical(work: Path, meta: dict, voice: Path, captions: list[dict], cfg: dict, out: Path,
                    banner: str, sub: str) -> Path:
    """Dựng clip dọc 1080x1920 từ giọng đọc + phụ đề. Dùng chung cho TikTok và YouTube Shorts."""
    from .render import mix_audio

    tk = cfg["tiktok"]
    tdir = work / sub
    tdir.mkdir(exist_ok=True)
    tcfg = cfg["thumbnail"]
    channel = cfg["channel"]["name"]

    rcfg = json.loads(json.dumps(cfg["render"]))
    rcfg["lead_in"], rcfg["tail"] = tk.get("lead_in", 0.2), tk.get("tail", 1.5)
    rcfg["audio"].update(fade_in=0.3, fade_out=1.5)
    total = rcfg["lead_in"] + ff.duration(voice) + rcfg["tail"]
    audio = mix_audio(voice, total, tdir / "mix.m4a", rcfg, seed=1)

    badge = (tk.get("badge") or "").replace("{channel_name}", channel).replace("{episode}", str(meta.get("episode", "")))
    frame = tiktok_frame(work / "thumb_bg.png", meta, tdir / "frame.png", tcfg,
                         banner.replace("{channel_name}", channel), badge)
    caps = caption_track(captions, rcfg["lead_in"], total, tdir / "captions",
                         tk.get("caption_font"), tk.get("caption_font_variation"))
    fps = tk.get("fps", 24)
    kbps = tk.get("max_video_kbps", 1000)
    ff.run([
        "-loop", "1", "-framerate", fps, "-i", frame,
        "-f", "concat", "-safe", "0", "-i", caps,
        "-i", audio,
        "-filter_complex", f"[0:v][1:v]overlay=0:0:format=auto,fps={fps},format=yuv420p[v]",
        "-map", "[v]", "-map", "2:a", "-t", f"{total:.3f}",
        # Giới hạn bitrate: clip 5 phút ~40 MB, vừa giới hạn 50 MB của bot Telegram
        "-c:v", "libx264", "-preset", cfg["render"].get("x264_preset") or "veryfast", "-tune", "stillimage",
        "-crf", "24", "-maxrate", kbps * 1000, "-bufsize", kbps * 2000,
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out,
    ])
    return out


def render_tiktok(work: Path, meta: dict, hook_wav: Path, captions: list[dict], cta_wav: Path | None,
                  cfg: dict) -> Path:
    from .tts import concat_wavs, silence

    tdir = work / "tiktok"
    tdir.mkdir(exist_ok=True)
    parts = [hook_wav]
    if cta_wav:
        parts += [silence(tdir / "pause.wav", 0.6), cta_wav]
    voice = concat_wavs(parts, tdir / "voice.wav", tdir / "voice.txt")
    banner = cfg["tiktok"].get("banner", "Nghe trọn bộ trên YouTube: {channel_name}")
    return render_vertical(work, meta, voice, captions, cfg, work / "tiktok.mp4", banner, "tiktok")


def cut_for_shorts(sentences: list[dict], captions: list[dict], budget: float) -> tuple[list[dict], list[dict]]:
    """Giữ các câu đầu của hook sao cho tổng ≤ budget giây; ưu tiên dừng ở câu kết thúc bằng '?' hoặc '…'
    (điểm treo tự nhiên) nếu nó nằm trong 70% cuối ngân sách."""
    kept = [s for s in sentences if s["end"] <= budget]
    if not kept:
        kept = sentences[:1]
    for i in range(len(kept) - 1, -1, -1):
        if kept[i]["text"].rstrip().endswith(("?", "…", "...")) and kept[i]["end"] >= budget * 0.7:
            kept = kept[: i + 1]
            break
    cutoff = kept[-1]["end"]
    return kept, [c for c in captions if c["end"] <= cutoff + 0.01]


def render_short(job, meta: dict) -> Path:
    """YouTube Shorts (≤ 3 phút): hook — cắt ở ranh giới câu nếu dài — + lời mời nghe bản đầy đủ.
    Trên YouTube Studio, gắn "Video liên quan" của Shorts tới video dài để người xem bấm sang ngay."""
    from .tts import concat_wavs, silence

    cfg = job.cfg
    scfg = cfg["shorts"]
    work = job.dir
    sdir = work / "shorts"
    sdir.mkdir(exist_ok=True)
    cta = work / "tts" / "cta_shorts" / "0000.norm.wav"
    if not cta.exists():
        cta = work / "tts" / "cta" / "0000.norm.wav"
    cta_dur = ff.duration(cta) + 0.6 if cta.exists() else 0
    tk = cfg["tiktok"]
    budget = scfg.get("max_seconds", 175) - tk.get("lead_in", 0.2) - tk.get("tail", 1.5) - cta_dur
    sentences = json.loads((work / "hook_sentences.json").read_text(encoding="utf-8"))
    captions = json.loads((work / "hook_captions.json").read_text(encoding="utf-8"))
    kept, caps = cut_for_shorts(sentences, captions, budget)
    pause = silence(sdir / "pause.wav", 0.25)
    parts: list[Path] = []
    for s in kept:
        parts += [Path(s["wav"]), pause]
    if cta.exists():
        parts += [silence(sdir / "pause_cta.wav", 0.35), cta]
    voice = concat_wavs(parts, sdir / "voice.wav", sdir / "voice.txt")
    return render_vertical(work, meta, voice, caps, cfg, work / "short.mp4",
                           scfg.get("banner", "Bản đầy đủ: bấm video liên quan ▼"), "shorts")
