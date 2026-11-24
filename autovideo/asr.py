"""Module 1b: Speech-to-Text bằng Faster-Whisper (large-v3 trên GPU)."""
from __future__ import annotations

import json
from pathlib import Path


def transcribe(audio: Path, out_json: Path, cfg: dict) -> str:
    """Bóc text tiếng Trung kèm timestamp. Ghi out_json, trả về toàn văn."""
    from faster_whisper import WhisperModel

    model = WhisperModel(cfg["model"], device=cfg["device"], compute_type=cfg["compute_type"])
    segments, info = model.transcribe(
        str(audio),
        language=cfg.get("language") or None,
        vad_filter=cfg.get("vad_filter", True),
        beam_size=5,
        # Ép Whisper xuất chữ giản thể có dấu câu, tránh câu dính liền
        initial_prompt="以下是普通话的句子，使用简体中文，带标点符号。",
    )
    items = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments]
    out_json.write_text(
        json.dumps({"language": info.language, "segments": items}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return segments_to_text(items)


def segments_to_text(segments: list[dict], pause_gap: float = 1.2) -> str:
    """Nối segment thành đoạn văn; khoảng lặng dài => xuống dòng (giữ nhịp nghỉ của bản gốc)."""
    lines: list[str] = []
    current = ""
    prev_end = None
    for seg in segments:
        if prev_end is not None and seg["start"] - prev_end > pause_gap and current:
            lines.append(current)
            current = ""
        current += seg["text"]
        prev_end = seg["end"]
    if current:
        lines.append(current)
    return "\n".join(lines)
