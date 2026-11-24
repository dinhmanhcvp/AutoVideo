"""Module 3: tạo giọng đọc tiếng Việt.

- engine "edge":    edge-tts (miễn phí, vi-VN-HoaiMyNeural / vi-VN-NamMinhNeural).
- engine "command": gọi lệnh ngoài bất kỳ (F5-TTS, XTTS-v2 voice cloning...) qua template.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
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


def _post_retry(url: str, retries: int = 4, **kw):
    import time

    import requests

    for attempt in range(retries):
        resp = requests.post(url, timeout=120, **kw)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(float(resp.headers.get("retry-after", 5 * (attempt + 1))))
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"TTS lỗi {resp.status_code}: {resp.text[:300]}")
        return resp
    raise RuntimeError(f"TTS thất bại sau {retries} lần: {url}")


def _google_one(text: str, out: Path, g: dict) -> None:
    """Google Cloud Text-to-Speech (giọng vi-VN Chirp 3 HD rất tự nhiên). Cần GOOGLE_TTS_API_KEY.
    Xem danh sách giọng: python -m autovideo voices --engine google"""
    import base64

    body = {
        "input": {"text": text},
        "voice": {"languageCode": "vi-VN", "name": g.get("voice", "vi-VN-Chirp3-HD-Charon")},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": g.get("speaking_rate", 1.0)},
    }
    resp = _post_retry("https://texttospeech.googleapis.com/v1/text:synthesize",
                       params={"key": os.environ["GOOGLE_TTS_API_KEY"]}, json=body)
    out.write_bytes(base64.b64decode(resp.json()["audioContent"]))


def _elevenlabs_one(text: str, out: Path, e: dict) -> None:
    """ElevenLabs (giọng biểu cảm nhất, có clone giọng). Cần ELEVENLABS_API_KEY và voice_id."""
    voice = e.get("voice_id")
    if not voice:
        raise ValueError("Thiếu tts.elevenlabs.voice_id (xem: python -m autovideo voices --engine elevenlabs)")
    model = e.get("model_id", "eleven_v3")
    body = {"text": text, "model_id": model}
    if model.endswith("v2_5"):  # chỉ dòng Flash/Turbo v2.5 nhận tham số ép ngôn ngữ
        body["language_code"] = "vi"
    if e.get("stability") is not None:
        body["voice_settings"] = {"stability": e["stability"]}
    resp = _post_retry(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                       params={"output_format": "mp3_44100_128"},
                       headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, json=body)
    out.write_bytes(resp.content)


def list_voices(engine: str) -> list[str]:
    import requests

    if engine == "edge":
        import edge_tts

        voices = asyncio.run(edge_tts.list_voices())
        return [f"{v['ShortName']}  ({v['Gender']})" for v in voices if v["Locale"] == "vi-VN"]
    if engine == "google":
        r = requests.get("https://texttospeech.googleapis.com/v1/voices",
                         params={"languageCode": "vi-VN", "key": os.environ["GOOGLE_TTS_API_KEY"]}, timeout=30)
        r.raise_for_status()
        return [f"{v['name']}  ({v.get('ssmlGender', '')})" for v in r.json().get("voices", [])]
    if engine == "elevenlabs":
        r = requests.get("https://api.elevenlabs.io/v1/voices",
                         headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=30)
        r.raise_for_status()
        return [f"{v['voice_id']}  {v['name']}" for v in r.json().get("voices", [])]
    raise ValueError(f"engine không hỗ trợ liệt kê giọng: {engine}")


def _quote(s: str) -> str:
    return subprocess.list2cmdline([s]) if os.name == "nt" else shlex.quote(s)


def _command_one(text: str, out: Path, template: str) -> None:
    text_file = out.with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")
    cmd = template.format(
        text_file=_quote(str(text_file)),
        text=_quote(text),
        out=_quote(str(out)),
        out_dir=_quote(str(out.parent)),
        out_name=_quote(out.name),
    )
    subprocess.run(cmd, shell=True, check=True)
    if not out.exists():
        raise RuntimeError(f"Lệnh TTS không tạo ra {out}: {cmd}")


def synth_pieces(texts: list[str], tdir: Path, cfg: dict, prefix: str = "") -> list[Path]:
    """Đọc từng đoạn -> wav mono 44.1 kHz đã chuẩn hóa. Đoạn đã có thì bỏ qua (chạy tiếp được)."""
    tdir.mkdir(parents=True, exist_ok=True)
    engine = cfg["engine"]
    ext = ".wav" if engine == "command" else ".mp3"
    wavs: list[Path] = []
    for i, text in enumerate(texts):
        raw = tdir / f"{prefix}{i:04d}{ext}"
        wav = tdir / f"{prefix}{i:04d}.norm.wav"
        if not wav.exists():
            if engine == "edge":
                asyncio.run(_edge_one(text, raw, cfg["voice"], cfg["rate"], cfg["pitch"]))
            elif engine == "google":
                _google_one(text, raw, cfg.get("google", {}))
            elif engine == "elevenlabs":
                _elevenlabs_one(text, raw, cfg.get("elevenlabs", {}))
            elif engine == "command":
                _command_one(text, raw, cfg["command"])
            else:
                raise ValueError(f"tts.engine không hỗ trợ: {engine}")
            ff.run(["-i", raw, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", wav])
        wavs.append(wav)
    return wavs


def silence(path: Path, seconds: float) -> Path:
    if not path.exists():
        ff.run(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", path])
    return path


def concat_wavs(parts: list[Path], out: Path, list_file: Path) -> Path:
    ff.run(["-f", "concat", "-safe", "0", "-i", ff.concat_list(parts, list_file), "-c", "copy", out])
    return out


def synthesize(script: str, work: Path, cfg: dict, out_name: str = "voice.wav") -> Path:
    """Đọc toàn bộ kịch bản -> work/<out_name> (mono 44.1kHz)."""
    tdir = work / "tts"
    chunks = split_for_tts(script, cfg["chunk_words"])
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    wavs = synth_pieces(chunks, tdir, cfg)
    print(f"  [tts] {len(wavs)} đoạn")
    gap = silence(tdir / f"gap_{cfg['gap_ms']}.wav", cfg["gap_ms"] / 1000)
    sequence: list[Path] = []
    for w in wavs:
        sequence += [w, gap]
    return concat_wavs(sequence, work / out_name, tdir / "list.txt")


_SENT = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in (p.strip() for p in text.splitlines()):
        if para:
            out.extend(s.strip() for s in _SENT.split(para) if s.strip())
    return out


def caption_units(sentence: str, max_words: int = 9) -> list[str]:
    """Cắt câu dài thành cụm phụ đề ngắn (ưu tiên cắt ở dấu phẩy) để đọc kịp trên điện thoại."""
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    units, cur = [], []
    for w in words:
        cur.append(w)
        if (len(cur) >= max_words) or (len(cur) >= max_words // 2 and w.endswith((",", ";", ":"))):
            units.append(" ".join(cur))
            cur = []
    if cur:
        if units and len(cur) < 3 and len(units[-1].split()) + len(cur) <= max_words + 2:
            units[-1] += " " + " ".join(cur)
        else:
            units.append(" ".join(cur))
    return units


def synthesize_timed(text: str, work: Path, cfg: dict, name: str, gap: float = 0.25) -> tuple[Path, list[dict]]:
    """Đọc từng câu để có mốc thời gian chính xác -> (<name>.wav, phụ đề [{start, end, text}])."""
    tdir = work / "tts" / name
    sentences = split_sentences(text)
    wavs = synth_pieces(sentences, tdir, cfg)
    pause = silence(tdir / "pause.wav", gap)
    captions, t, sequence, sent_info = [], 0.0, [], []
    for sent, wav in zip(sentences, wavs):
        dur = ff.duration(wav)
        sent_info.append({"text": sent, "start": round(t, 3), "end": round(t + dur, 3), "wav": str(wav)})
        units = caption_units(sent)
        total_chars = sum(len(u) for u in units)
        start = t
        for u in units:  # trong 1 câu: chia thời gian theo độ dài chữ
            d = dur * len(u) / total_chars
            captions.append({"start": round(start, 3), "end": round(start + d, 3), "text": u})
            start += d
        t += dur + gap
        sequence += [wav, pause]
    out = concat_wavs(sequence, work / f"{name}.wav", tdir / "list.txt")
    (work / f"{name}_captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / f"{name}_sentences.json").write_text(json.dumps(sent_info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  [tts] {name}: {len(sentences)} câu, {t:.0f}s")
    return out, captions
