"""Module 1b: Speech-to-Text tiếng Trung.

engine:
- local:  Faster-Whisper trên máy (large-v3 + GPU; máy yếu dùng small/medium + cpu/int8).
- groq:   Whisper large-v3 trên cloud Groq (rất nhanh, có free tier) — cần GROQ_API_KEY.
- gemini: Gemini nghe audio rồi chép lại — cần GEMINI_API_KEY.
Hai engine cloud: audio được nén mono 16 kHz và cắt thành đoạn ngắn trước khi gửi, nên máy yếu vẫn chạy nhẹ.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import ff

ZH_PROMPT = "以下是普通话的句子，使用简体中文，带标点符号。"


def transcribe(audio: Path, out_json: Path, cfg: dict) -> str:
    """Bóc text tiếng Trung kèm timestamp. Ghi out_json, trả về toàn văn."""
    engine = cfg.get("engine", "local")
    if engine == "local":
        segments = _local(audio, cfg)
    elif engine in ("groq", "gemini"):
        chunks = split_audio(audio, out_json.parent / "asr_chunks", cfg.get("chunk_minutes", 10))
        fn = _groq_chunk if engine == "groq" else _gemini_chunk
        segments = []
        for i, (path, offset) in enumerate(chunks):
            cache = path.with_suffix(".json")
            if cache.exists():
                part = json.loads(cache.read_text(encoding="utf-8"))
            else:
                part = fn(path, cfg)
                cache.write_text(json.dumps(part, ensure_ascii=False), encoding="utf-8")
            segments += [{**s, "start": round(s["start"] + offset, 2), "end": round(s["end"] + offset, 2)} for s in part]
            print(f"  [asr] {i + 1}/{len(chunks)}")
    else:
        raise ValueError(f"asr.engine không hỗ trợ: {engine}")
    out_json.write_text(json.dumps({"engine": engine, "segments": segments}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return segments_to_text(segments)


def _local(audio: Path, cfg: dict) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel(cfg["model"], device=cfg["device"], compute_type=cfg["compute_type"],
                         cpu_threads=cfg.get("cpu_threads", 0))
    segments, _ = model.transcribe(
        str(audio),
        language=cfg.get("language") or None,
        vad_filter=cfg.get("vad_filter", True),
        beam_size=cfg.get("beam_size", 5),
        initial_prompt=ZH_PROMPT,  # ép giản thể có dấu câu, tránh câu dính liền
    )
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments]


def split_audio(audio: Path, out_dir: Path, minutes: float) -> list[tuple[Path, float]]:
    """Nén mono 16 kHz mp3 32 kbps (~2.4 MB / 10 phút) và cắt đoạn. Trả về [(file, offset_giây)]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = sorted(out_dir.glob("part_*.mp3"))
    if not parts:
        ff.run(["-i", audio, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
                "-f", "segment", "-segment_time", int(minutes * 60), "-reset_timestamps", "1",
                out_dir / "part_%03d.mp3"])
        parts = sorted(out_dir.glob("part_*.mp3"))
    result, offset = [], 0.0
    for p in parts:
        result.append((p, offset))
        offset += ff.duration(p)
    return result


def _groq_chunk(path: Path, cfg: dict, retries: int = 5) -> list[dict]:
    import os

    import requests

    for attempt in range(retries):
        with open(path, "rb") as f:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                files={"file": (path.name, f, "audio/mpeg")},
                data={"model": cfg.get("groq_model", "whisper-large-v3"), "language": cfg.get("language", "zh"),
                      "response_format": "verbose_json", "prompt": ZH_PROMPT, "temperature": "0"},
                timeout=600,
            )
        if resp.status_code == 429 or resp.status_code >= 500:  # free tier giới hạn số giây audio/giờ
            wait = float(resp.headers.get("retry-after", 30 * (attempt + 1)))
            print(f"  [asr] Groq bận/giới hạn, chờ {wait:.0f}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        return [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in data.get("segments", [])]
    raise RuntimeError(f"Groq ASR thất bại sau {retries} lần: {path}")


def _gemini_chunk(path: Path, cfg: dict) -> list[dict]:
    from google import genai

    client = genai.Client()
    uploaded = client.files.upload(file=str(path))
    resp = client.models.generate_content(
        model=cfg.get("gemini_model", "gemini-2.5-flash"),
        contents=[uploaded, "逐字转写这段音频的全部内容，使用简体中文并加上标点符号。按自然段落换行。只输出转写文本，不要任何说明。"],
    )
    try:
        client.files.delete(name=uploaded.name)
    except Exception:
        pass
    # Gemini không trả timestamp: coi mỗi đoạn văn là 1 segment, rải đều trong đoạn audio
    paras = [p.strip() for p in (resp.text or "").splitlines() if p.strip()]
    dur = ff.duration(path)
    step = dur / max(len(paras), 1)
    return [{"start": i * step, "end": (i + 1) * step, "text": p} for i, p in enumerate(paras)]


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
