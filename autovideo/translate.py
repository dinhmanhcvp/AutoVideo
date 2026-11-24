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

def build_system_prompt(cfg: dict, extra_glossary: dict | None = None, characters: str = "") -> str:
    genre = cfg["genre"]
    genre_rules = load_prompt(f"genres/{genre}.md")
    glossary = dict(extra_glossary or {})
    glossary.update(cfg["llm"].get("glossary") or {})  # bảng của kênh ưu tiên hơn bảng tự trích
    glossary_txt = "\n".join(f"- {k} → {v}" for k, v in glossary.items()) or "(chưa có)"
    return fill(
        load_prompt("translate_base.md"),
        channel_name=cfg["channel"]["name"],
        genre_rules=genre_rules,
        glossary=glossary_txt,
        characters=characters or "(chưa có)",
    )


_CJK = re.compile(r"[\u4e00-\u9fff]")
_REFUSAL = re.compile(r"(I can't|I cannot|I'm sorry|Xin lỗi, tôi không thể|tôi không thể (giúp|dịch))", re.I)


def qa_chunk(zh: str, vi: str) -> list[str]:
    """Kiểm tra nhanh 1 đoạn dịch (không tốn LLM). Tỷ lệ ký tự Việt/Trung thường 2.5–4.5."""
    issues = []
    cjk = len(_CJK.findall(vi))
    if cjk > 3:
        issues.append(f"còn {cjk} chữ Hán chưa dịch")
    zh_len = max(1, len(_CJK.findall(zh)))
    ratio = len(vi) / zh_len
    if zh_len > 80 and ratio < 1.5:
        issues.append(f"bản dịch quá ngắn so với bản gốc (tỷ lệ {ratio:.1f}) — có thể bị lược bỏ")
    if zh_len > 80 and ratio > 7:
        issues.append(f"bản dịch dài bất thường (tỷ lệ {ratio:.1f}) — có thể bị thêm thắt")
    if _REFUSAL.search(vi[:300]):
        issues.append("có dấu hiệu từ chối/giải thích thay vì dịch")
    return issues


def translate(llm, source_text: str, cfg: dict, progress_file: Path | None = None,
              extra_glossary: dict | None = None, characters: str = "", qa_file: Path | None = None) -> str:
    """Dịch tuần tự từng chunk, gửi kèm đuôi bản dịch trước để giữ xưng hô/tên riêng nhất quán.
    Mỗi chunk qua QA; lỗi thì dịch lại (tối đa llm.qa_retries lần) kèm mô tả lỗi.
    progress_file: lưu từng chunk đã dịch để chạy tiếp được nếu bị ngắt giữa chừng."""
    system = build_system_prompt(cfg, extra_glossary, characters)
    chunks = split_source(source_text, cfg["llm"]["source_chunk_chars"])
    done: list[str] = []
    if progress_file and progress_file.exists():
        done = json.loads(progress_file.read_text(encoding="utf-8"))
    qa_log = json.loads(qa_file.read_text(encoding="utf-8")) if qa_file and qa_file.exists() else {}
    ctx_chars = cfg["llm"].get("context_chars", 600)
    retries = cfg["llm"].get("qa_retries", 2)

    for i in range(len(done), len(chunks)):
        previous = "\n".join(done)[-ctx_chars:] if done else ""
        base = ""
        if previous:
            base += f"<ban_dich_truoc_do>\n{previous}\n</ban_dich_truoc_do>\n\n"
        base += (
            f"Dịch đoạn {i + 1}/{len(chunks)} sau sang tiếng Việt, ĐẦY ĐỦ từng ý, nối tiếp mạch truyện:\n"
            f"<doan_goc>\n{chunks[i]}\n</doan_goc>"
        )
        best, best_issues = None, None
        for attempt in range(retries + 1):
            user = base
            if best_issues:
                user += ("\n\nLần dịch trước bị lỗi: " + "; ".join(best_issues)
                         + ". Hãy dịch lại đầy đủ, chỉ trả về bản dịch.")
            vi = llm.complete(system, user)
            issues = qa_chunk(chunks[i], vi)
            if best is None or len(issues) < len(best_issues):
                best, best_issues = vi, issues
            if not issues:
                break
        if best_issues:
            qa_log[str(i)] = best_issues
            print(f"  [dịch] ⚠ đoạn {i + 1}: {'; '.join(best_issues)}")
        done.append(best)
        if progress_file:
            progress_file.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        if qa_file:
            qa_file.write_text(json.dumps(qa_log, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  [dịch] {i + 1}/{len(chunks)}")
    return "\n\n".join(done)


def make_metadata(llm, vi_text: str, cfg: dict) -> dict:
    ch = cfg["channel"]
    extra = []
    if ch.get("intro"):
        extra.append(
            '- "intro": lời dẫn 35–55 chữ (dưới 20 giây — người nghe vừa qua hook, đừng bắt họ chờ): '
            "chào ngắn gọn bằng giọng kênh, nhắc tên truyện, mời nghe. Không tóm tắt lại hook."
        )
    if ch.get("outro"):
        extra.append(
            '- "outro": lời bình cuối truyện 80–120 chữ mang dấu ấn riêng của kênh: cảm nhận/bài học, '
            "một câu hỏi mời bình luận, mời đăng ký và gợi ý nghe tiếp truyện cùng thể loại trong danh sách phát."
        )
    system = fill(
        load_prompt("metadata.md"),
        channel_name=ch["name"],
        scenes=cfg["render"]["still"]["scenes"],
        intro_outro="\n".join(extra),
        visual_style=ch.get("visual_style", ""),
    )
    meta = extract_json(llm.complete(system, "", max_tokens=12000, doc=f"<truyen>\n{vi_text}\n</truyen>"))
    return normalize_metadata(meta, cfg)


def _clean_highlights(story: str, hl) -> list[str]:
    hl = [hl] if isinstance(hl, str) else (hl or [])
    return [h for h in hl if h and h.upper() in story.upper()][:2]


def normalize_metadata(meta: dict, cfg: dict) -> dict:
    variants = []
    for v in meta.get("title_variants") or []:
        if isinstance(v, dict) and v.get("story_title"):
            variants.append({"story_title": v["story_title"].strip(),
                             "thumb_highlight": _clean_highlights(v["story_title"], v.get("thumb_highlight")),
                             "angle": v.get("angle", "")})
    if not variants and meta.get("story_title"):  # định dạng cũ: 1 tên truyện
        variants.append({"story_title": meta["story_title"],
                         "thumb_highlight": _clean_highlights(meta["story_title"], meta.get("thumb_highlight")),
                         "angle": ""})
    thumb = meta.get("thumb_text") or [meta.get("youtube_title", "")]
    if isinstance(thumb, str):
        words = thumb.split()
        half = (len(words) + 1) // 2
        thumb = [" ".join(words[:half]), " ".join(words[half:])]
    meta["thumb_text"] = [t for t in thumb if t][:2]
    if not variants:
        variants.append({"story_title": " ".join(meta["thumb_text"]) or meta.get("youtube_title", ""),
                         "thumb_highlight": [], "angle": ""})
    meta["title_variants"] = variants[:3]
    meta["story_title"] = variants[0]["story_title"]
    meta["thumb_highlight"] = variants[0]["thumb_highlight"]
    style = cfg["channel"].get("visual_style", "")
    suffix = f", {style}" if style else ""
    meta["image_prompt"] = (meta.get("image_prompt") or "") + suffix
    scenes = meta.get("scene_prompts") or [meta["image_prompt"]]
    meta["scene_prompts"] = [s + suffix if style and style not in s else s for s in scenes]
    meta.setdefault("tags", [])
    meta.setdefault("description", "")
    meta.setdefault("chapters", [])
    meta.setdefault("pinned_comment", "")
    tags = [h if h.startswith("#") else "#" + h for h in (meta.get("hashtags") or [])]
    meta["hashtags"] = [re.sub(r"\s+", "", h) for h in tags][:3] or ["#truyenaudio"]
    return meta


def select_variant(meta: dict, index: int) -> dict:
    v = meta["title_variants"][index]
    meta["story_title"], meta["thumb_highlight"] = v["story_title"], v["thumb_highlight"]
    meta["variant"] = index
    return meta


def compose_script(vi_text: str, meta: dict, bridge: str = "") -> str:
    """Kịch bản chính = câu chuyển từ hook (nếu có) + lời dẫn + truyện + lời bình."""
    parts = [bridge, meta.get("intro"), vi_text, meta.get("outro")]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def final_title(meta: dict, cfg: dict) -> str:
    """Tiêu đề YouTube theo mẫu của kênh, vd "[Truyện Audio] {story_title} (Full) | {channel_name}"."""
    tmpl = cfg["channel"].get("title_template")
    if not tmpl or not meta.get("story_title"):
        return meta.get("youtube_title", "")[:100]
    title = fill(tmpl, story_title=meta["story_title"], channel_name=cfg["channel"]["name"],
                 episode=meta.get("episode", ""))
    if len(title) > 100:  # giới hạn YouTube: bỏ phần đuôi kênh trước, rồi mới cắt
        title = fill(tmpl.split("|")[0].strip(), story_title=meta["story_title"],
                     channel_name=cfg["channel"]["name"], episode=meta.get("episode", ""))
    return title[:100]
