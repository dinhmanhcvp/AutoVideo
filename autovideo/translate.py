"""Module 2: dịch & biên tập văn phong theo thể loại, sinh metadata/intro/outro, chia chunk cho TTS."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .llm import extract_json

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

_ZH_SENT_END = re.compile(r"(?<=[。！？!?…；;」』”])")
_VI_SENT_END = re.compile(r"(?<=[.!?…])\s+")


def fill(template: str, **values) -> str:
    """Thay {key} an toàn (không đụng các dấu ngoặc nhọn khác trong prompt)."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- chia đoạn

def split_source(text: str, max_chars: int) -> list[str]:
    """Chia văn bản tiếng Trung thành chunk <= max_chars, ưu tiên ranh giới đoạn rồi câu."""
    pieces: list[str] = []
    for para in (p.strip() for p in text.splitlines()):
        if not para:
            continue
        if len(para) <= max_chars:
            pieces.append(para)
            continue
        for sent in _ZH_SENT_END.split(para):
            sent = sent.strip()
            while len(sent) > max_chars:  # câu không dấu câu (lỗi ASR) — cắt cứng
                pieces.append(sent[:max_chars])
                sent = sent[max_chars:]
            if sent:
                pieces.append(sent)
    return _pack(pieces, max_chars, sep="\n", size=len, sep_cost=1)


def split_for_tts(text: str, max_words: int) -> list[str]:
    """Chia bản Việt thành đoạn ~max_words chữ, cắt ở ranh giới câu để TTS không hụt hơi."""
    sentences: list[str] = []
    for para in (p.strip() for p in text.splitlines()):
        if para:
            sentences.extend(s.strip() for s in _VI_SENT_END.split(para) if s.strip())
    return _pack(sentences, max_words, sep=" ", size=lambda s: len(s.split()))


def _pack(items: list[str], limit: int, sep: str, size, sep_cost: int = 0) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    used = 0
    for item in items:
        n = size(item) + (sep_cost if buf else 0)
        if buf and used + n > limit:
            chunks.append(sep.join(buf))
            buf, used = [], 0
            n = size(item)
        buf.append(item)
        used += n
    if buf:
        chunks.append(sep.join(buf))
    return chunks


# ---------------------------------------------------------------- dịch

def build_system_prompt(cfg: dict) -> str:
    genre = cfg["genre"]
    genre_rules = load_prompt(f"genres/{genre}.md")
    glossary = cfg["llm"].get("glossary") or {}
    glossary_txt = "\n".join(f"- {k} → {v}" for k, v in glossary.items()) or "(chưa có)"
    return fill(
        load_prompt("translate_base.md"),
        channel_name=cfg["channel"]["name"],
        genre_rules=genre_rules,
        glossary=glossary_txt,
    )


def translate(llm, source_text: str, cfg: dict, progress_file: Path | None = None) -> str:
    """Dịch tuần tự từng chunk, gửi kèm đuôi bản dịch trước để giữ xưng hô/tên riêng nhất quán.
    progress_file: lưu từng chunk đã dịch để chạy tiếp được nếu bị ngắt giữa chừng."""
    system = build_system_prompt(cfg)
    chunks = split_source(source_text, cfg["llm"]["source_chunk_chars"])
    done: list[str] = []
    if progress_file and progress_file.exists():
        done = json.loads(progress_file.read_text(encoding="utf-8"))
    ctx_chars = cfg["llm"].get("context_chars", 600)

    for i in range(len(done), len(chunks)):
        previous = "\n".join(done)[-ctx_chars:] if done else ""
        user = ""
        if previous:
            user += f"<ban_dich_truoc_do>\n{previous}\n</ban_dich_truoc_do>\n\n"
        user += (
            f"Dịch đoạn {i + 1}/{len(chunks)} sau sang tiếng Việt, nối tiếp mạch truyện:\n"
            f"<doan_goc>\n{chunks[i]}\n</doan_goc>"
        )
        done.append(llm.complete(system, user))
        if progress_file:
            progress_file.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  [dịch] {i + 1}/{len(chunks)}")
    return "\n\n".join(done)


def make_metadata(llm, vi_text: str, cfg: dict) -> dict:
    ch = cfg["channel"]
    extra = []
    if ch.get("intro"):
        extra.append(
            '- "intro": lời dẫn ~70–90 chữ (khoảng 30 giây) mở đầu video, giọng kênh, chào người nghe, '
            "gợi tò mò về câu chuyện hôm nay, không tiết lộ kết."
        )
    if ch.get("outro"):
        extra.append(
            '- "outro": lời bình cuối truyện ~80–120 chữ: cảm nhận/bài học riêng của kênh, '
            "đặt một câu hỏi để người nghe bình luận, mời đăng ký kênh."
        )
    system = fill(
        load_prompt("metadata.md"),
        channel_name=ch["name"],
        scenes=cfg["render"]["still"]["scenes"],
        intro_outro="\n".join(extra),
        visual_style=ch.get("visual_style", ""),
    )
    meta = extract_json(llm.complete(system, f"<truyen>\n{vi_text}\n</truyen>", max_tokens=8000))
    return normalize_metadata(meta, cfg)


def normalize_metadata(meta: dict, cfg: dict) -> dict:
    thumb = meta.get("thumb_text") or [meta.get("youtube_title", "")]
    if isinstance(thumb, str):
        words = thumb.split()
        half = (len(words) + 1) // 2
        thumb = [" ".join(words[:half]), " ".join(words[half:])]
    meta["thumb_text"] = [t for t in thumb if t][:2]
    style = cfg["channel"].get("visual_style", "")
    suffix = f", {style}" if style else ""
    meta["image_prompt"] = (meta.get("image_prompt") or "") + suffix
    scenes = meta.get("scene_prompts") or [meta["image_prompt"]]
    meta["scene_prompts"] = [s + suffix if style and style not in s else s for s in scenes]
    meta.setdefault("tags", [])
    meta.setdefault("description", "")
    return meta


def compose_script(vi_text: str, meta: dict) -> str:
    """Kịch bản đọc cuối cùng = intro + truyện + outro."""
    parts = [meta.get("intro"), vi_text, meta.get("outro")]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())
