"""Module 3: tạo giọng đọc tiếng Việt.

- engine "edge":    edge-tts (miễn phí, vi-VN-HoaiMyNeural / vi-VN-NamMinhNeural).
- engine "command": gọi lệnh ngoài bất kỳ (F5-TTS, XTTS-v2 voice cloning...) qua template.
"""
from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
from pathlib import Path

from . import ff
from .translate import split_for_tts


async def _edge_one(text: str, out: Path, voice: str, rate: str, pitch: str, retries: int = 3) -> None:
    import edge_tts

    for attempt in range(retries):
        try:
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out))
            return
        except Exception:  # mạng chập chờn — thử lại
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 * (attempt + 1))


def _command_one(text: str, out: Path, template: str) -> None:
    text_file = out.with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")
    cmd = template.format(
        text_file=shlex.quote(str(text_file)),
        text=shlex.quote(text),
        out=shlex.quote(str(out)),
        out_dir=shlex.quote(str(out.parent)),
        out_name=shlex.quote(out.name),
    )
    subprocess.run(cmd, shell=True, check=True)
    if not out.exists():
        raise RuntimeError(f"Lệnh TTS không tạo ra {out}: {cmd}")


def synthesize(script: str, work: Path, cfg: dict) -> Path:
    """Đọc toàn bộ kịch bản -> work/voice.wav (mono 44.1kHz). Chunk đã có sẽ được bỏ qua."""
    tdir = work / "tts"
    tdir.mkdir(parents=True, exist_ok=True)
    chunks = split_for_tts(script, cfg["chunk_words"])
    (tdir / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")

    engine = cfg["engine"]
    ext = ".mp3" if engine == "edge" else ".wav"
    wavs: list[Path] = []
    for i, text in enumerate(chunks):
        raw = tdir / f"{i:04d}{ext}"
        wav = tdir / f"{i:04d}.norm.wav"
        if not wav.exists():
            if engine == "edge":
                asyncio.run(_edge_one(text, raw, cfg["voice"], cfg["rate"], cfg["pitch"]))
            elif engine == "command":
                _command_one(text, raw, cfg["command"])
            else:
                raise ValueError(f"tts.engine không hỗ trợ: {engine}")
            ff.run(["-i", raw, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", wav])
        wavs.append(wav)
        print(f"  [tts] {i + 1}/{len(chunks)}")

    gap = tdir / "gap.wav"
    ff.run(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", cfg["gap_ms"] / 1000, "-c:a", "pcm_s16le", gap])
    sequence: list[Path] = []
    for w in wavs:
        sequence += [w, gap]
    out = work / "voice.wav"
    ff.run(["-f", "concat", "-safe", "0", "-i", ff.concat_list(sequence, tdir / "list.txt"), "-c", "copy", out])
    return out
