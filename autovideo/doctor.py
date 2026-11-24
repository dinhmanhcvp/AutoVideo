"""`python -m autovideo doctor`: kiểm tra mọi thứ cần để chạy theo đúng config hiện tại và chỉ cách sửa.
`--online` gọi thử thật từng dịch vụ (LLM, giọng đọc, Telegram) — tốn vài đồng."""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

OK, WARN, FAIL = "✔", "⚠", "✘"


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, what: str, fix: str = ""):
        self.rows.append((status, what, fix))
        line = f" {status} {what}"
        if fix and status != OK:
            line += f"\n     → {fix}"
        print(line)

    @property
    def failed(self) -> int:
        return sum(1 for s, _, _ in self.rows if s == FAIL)


def _module(r: Report, name: str, pip: str, why: str):
    try:
        importlib.import_module(name)
        r.add(OK, f"thư viện {pip}")
    except ImportError:
        r.add(FAIL, f"thiếu thư viện {pip} ({why})", f"pip install {pip}")


def _key(r: Report, var: str, why: str, how: str):
    if os.environ.get(var):
        r.add(OK, f"{var} đã đặt")
    else:
        r.add(FAIL, f"thiếu {var} ({why})", f"thêm dòng {var}=... vào file .env — {how}")


def active_topics(cfg: dict) -> list[dict]:
    return [t for t in cfg.get("topics") or [] if t.get("enabled", True) is not False]


def run_doctor(cfg: dict, online: bool = False) -> int:
    from .auto import topic_config

    r = Report()
    print("== Hệ thống")
    if sys.version_info >= (3, 10):
        r.add(OK, f"Python {sys.version.split()[0]}")
    else:
        r.add(FAIL, f"Python {sys.version.split()[0]} quá cũ", "cài Python 3.10+ (python.org)")
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool):
            r.add(OK, tool)
        else:
            r.add(FAIL, f"không tìm thấy {tool}", "Windows: winget install Gyan.FFmpeg  (rồi mở lại cửa sổ lệnh)")
    if shutil.which("ffmpeg"):
        from .ff import encoder_works

        r.add(OK if encoder_works("h264_nvenc") else WARN,
              "GPU NVIDIA (NVENC) — render nhanh" if encoder_works("h264_nvenc") else "không có NVENC — render bằng CPU",
              "không bắt buộc; máy yếu nên dùng config.lite.yaml")

    topics = [topic_config(cfg, t) for t in active_topics(cfg)] or [cfg]
    print("\n== Thư viện & khóa API theo config")
    _module(r, "yaml", "PyYAML", "đọc config")
    _module(r, "PIL", "Pillow", "thumbnail")
    _module(r, "yt_dlp", "yt-dlp", "tải truyện")
    _module(r, "requests", "requests", "gọi API")

    llm = cfg["llm"]["provider"]
    if llm == "anthropic":
        _module(r, "anthropic", "anthropic", "dịch bằng Claude")
        _key(r, "ANTHROPIC_API_KEY", "dịch, viết hook", "lấy ở console.anthropic.com → API Keys")
    else:
        _module(r, "google.genai", "google-genai", "dịch bằng Gemini")
        _key(r, "GEMINI_API_KEY", "dịch bằng Gemini", "lấy ở aistudio.google.com → Get API key")

    asr = cfg["asr"].get("engine", "local")
    if asr == "local":
        _module(r, "faster_whisper", "faster-whisper", "bóc băng trên máy")
    elif asr == "groq":
        _key(r, "GROQ_API_KEY", "bóc băng trên cloud", "lấy miễn phí ở console.groq.com → API Keys")
    elif asr == "gemini":
        _key(r, "GEMINI_API_KEY", "bóc băng bằng Gemini", "aistudio.google.com")

    engines = {t["tts"]["engine"] for t in topics}
    if "edge" in engines:
        _module(r, "edge_tts", "edge-tts", "giọng đọc miễn phí")
    if "google" in engines:
        _key(r, "GOOGLE_TTS_API_KEY", "giọng Google Chirp 3 HD",
             "console.cloud.google.com → bật Cloud Text-to-Speech API → Credentials → API key")
    if "elevenlabs" in engines:
        _key(r, "ELEVENLABS_API_KEY", "giọng ElevenLabs", "elevenlabs.io → Profile → API Keys")

    img = cfg["thumbnail"].get("image_engine", "placeholder")
    if img == "cloud":
        _module(r, "google.genai", "google-genai", "vẽ ảnh cloud")
        _key(r, "GEMINI_API_KEY", "vẽ ảnh thumbnail bằng Google Imagen", "aistudio.google.com (cần bật thanh toán)")
    elif img == "placeholder":
        r.add(WARN, "ảnh nền đang là ảnh giữ chỗ (gradient)",
              "đặt thumbnail.image_engine: cloud (hoặc comfyui) để có ảnh minh họa thật — rất quan trọng cho CTR")
    elif img == "comfyui":
        try:
            import urllib.request

            urllib.request.urlopen(cfg["thumbnail"]["comfyui"]["url"], timeout=3)
            r.add(OK, "ComfyUI đang chạy")
        except Exception:
            r.add(FAIL, "không kết nối được ComfyUI", "mở ComfyUI trước khi chạy, kiểm tra thumbnail.comfyui.url")

    if cfg.get("review", {}).get("enabled"):
        _key(r, "TELEGRAM_BOT_TOKEN", "duyệt video qua điện thoại", "nhắn @BotFather → /newbot")
        if cfg["review"].get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID"):
            r.add(OK, "chat_id Telegram")
        else:
            r.add(FAIL, "thiếu review.chat_id", "chạy `python -m autovideo bot`, nhắn /id cho bot, điền số vào config")
    if cfg.get("youtube", {}).get("enabled"):
        _module(r, "googleapiclient", "google-api-python-client", "upload YouTube")
        _module(r, "google_auth_oauthlib", "google-auth-oauthlib", "đăng nhập YouTube")
        if Path(cfg["youtube"]["client_secrets"]).exists():
            r.add(OK, "OAuth client YouTube")
        else:
            r.add(FAIL, f"thiếu {cfg['youtube']['client_secrets']}", "xem README mục 'Upload YouTube tự động'")

    print("\n== Tài nguyên kênh")
    for key in ("font", "badge_font"):
        f = cfg["thumbnail"].get(key)
        if f and Path(f).exists():
            r.add(OK, f"font {Path(f).name}")
        else:
            r.add(WARN, f"chưa có font {f}", "python scripts/get_fonts.py")
    mascot = cfg["thumbnail"].get("mascot")
    r.add(OK if mascot and Path(mascot).exists() else WARN, "mascot/logo kênh",
          f"đặt PNG nền trong suốt tại {mascot} — giúp người xem nhận ra kênh")
    music = Path(cfg["render"]["audio"]["music_dir"])
    n_music = len([p for p in music.glob("*") if p.suffix.lower() in {".mp3", ".m4a", ".wav", ".flac", ".ogg"}]) \
        if music.exists() else 0
    r.add(OK if n_music >= 5 else WARN, f"nhạc nền: {n_music} bài",
          f"thêm ≥ 5 bài nhạc không bản quyền vào {music} (YouTube Audio Library là nguồn an toàn)")
    for t in topics:
        if t["render"]["mode"] == "footage":
            folder = Path(t["render"]["footage"]["dir"]) / (t["render"]["footage"].get("tone") or "")
            n = len(list(folder.glob("*.mp4"))) if folder.exists() else 0
            r.add(OK if n >= 8 else FAIL if n == 0 else WARN, f"footage cho {t.get('_topic')}: {n} clip ({folder})",
                  "cần ≥ 8 clip cùng tone để xáo trộn không lặp")

    if online:
        print("\n== Gọi thử dịch vụ (online)")
        _online(r, cfg, topics)

    print(f"\n{'✅ Sẵn sàng chạy!' if not r.failed else f'❌ Còn {r.failed} lỗi cần sửa ở trên.'}")
    return 1 if r.failed else 0


def _online(r: Report, cfg: dict, topics: list[dict]):
    try:
        from .llm import make_llm

        out = make_llm(cfg["llm"]).complete("Trả lời đúng một từ.", "Viết chữ OK.", max_tokens=2000)
        r.add(OK if "OK" in out.upper() else WARN, f"LLM {cfg['llm']['model']} trả lời: {out[:20]!r}")
    except Exception as e:
        r.add(FAIL, f"LLM lỗi: {str(e)[:150]}", "kiểm tra API key / số dư tài khoản")
    try:
        from .tts import synth_pieces

        tmp = Path(tempfile.mkdtemp())
        wav = synth_pieces(["Xin chào, đây là thử giọng đọc."], tmp, topics[0]["tts"])[0]
        r.add(OK, f"giọng đọc {topics[0]['tts']['engine']} → {wav}")
    except Exception as e:
        r.add(FAIL, f"giọng đọc lỗi: {str(e)[:150]}", "kiểm tra tts.engine và key")
    if cfg.get("review", {}).get("enabled"):
        try:
            from .telegram import Telegram

            me = Telegram(cfg["review"].get("bot_token"), cfg["review"].get("chat_id")).call("getMe")
            r.add(OK, f"bot Telegram @{me.get('username')}")
        except Exception as e:
            r.add(FAIL, f"Telegram lỗi: {str(e)[:150]}", "kiểm tra TELEGRAM_BOT_TOKEN")
