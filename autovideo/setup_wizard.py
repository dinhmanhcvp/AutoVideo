"""`python -m autovideo setup`: hỏi vài câu rồi tự tạo config.yaml (chỉ chứa các lựa chọn của bạn,
phần còn lại lấy mặc định từ config.example.yaml) và .env (khóa API). Chạy lại bất cứ lúc nào để đổi."""
from __future__ import annotations

import getpass
import os
import shutil
from pathlib import Path

import yaml

from .config import load_config


def ask(prompt: str, default: str = "", input_fn=input) -> str:
    hint = f" [{default}]" if default else ""
    value = input_fn(f"{prompt}{hint}: ").strip()
    return value or default


def choose(prompt: str, options: list[tuple[str, str]], default: int = 1, input_fn=input) -> str:
    print(f"\n{prompt}")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    while True:
        raw = ask("Chọn số", str(default), input_fn)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print("  ↳ nhập một số trong danh sách")


def yes(prompt: str, default: bool = True, input_fn=input) -> bool:
    raw = ask(f"{prompt} (c/k)", "c" if default else "k", input_fn).lower()
    return raw.startswith(("c", "y"))


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = ["# Khóa API của AutoVideo — KHÔNG chia sẻ file này, không đưa lên GitHub"]
    lines += [f"{k}={v}" for k, v in values.items() if v]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


KEY_HELP = {
    "ANTHROPIC_API_KEY": "Claude — console.anthropic.com → API Keys",
    "GEMINI_API_KEY": "Google AI Studio — aistudio.google.com → Get API key",
    "GROQ_API_KEY": "Groq (miễn phí) — console.groq.com → API Keys",
    "GOOGLE_TTS_API_KEY": "Google Cloud — bật Cloud Text-to-Speech API → Credentials → Create API key",
    "ELEVENLABS_API_KEY": "ElevenLabs — elevenlabs.io → Profile → API Keys",
    "TELEGRAM_BOT_TOKEN": "Telegram — nhắn @BotFather, gõ /newbot, làm theo hướng dẫn",
}


def run_setup(config_path: str = "config.yaml", env_path: str = ".env", input_fn=input, secret_fn=None) -> dict:
    secret_fn = secret_fn or (lambda p: getpass.getpass(p))
    base = load_config()
    print("=" * 60)
    print(" CÀI ĐẶT AUTOVIDEO — trả lời vài câu, Enter để giữ mặc định")
    print("=" * 60)
    ov: dict = {"channel": {}, "asr": {}, "llm": {}, "tts": {}, "thumbnail": {}, "render": {},
                "review": {}, "youtube": {}}
    needed: list[str] = []

    ov["channel"]["name"] = ask("\nTên kênh YouTube của bạn", base["channel"]["name"], input_fn)

    strong = choose("Máy tính của bạn?", [
        ("strong", "Có card NVIDIA ≥ 8 GB VRAM (bóc băng + render trên máy, tiết kiệm phí)"),
        ("weak", "Máy yếu / laptop / không có card rời (đẩy việc nặng lên cloud)")], 2, input_fn) == "strong"
    if strong:
        ov["asr"] = {"engine": "local", "model": "large-v3", "device": "cuda", "compute_type": "float16"}
    else:
        ov["asr"] = {"engine": "groq"}
        ov["render"].update({"x264_preset": "superfast", "fps": 24, "still": {"upscale": 1.5}})
        needed.append("GROQ_API_KEY")

    topics = base["topics"]
    print("\nChủ đề kênh (nên chọn 1–2 chủ đề cho kênh mới để YouTube hiểu kênh nhanh):")
    for i, t in enumerate(topics, 1):
        print(f"  {i}. {t.get('label', t['name'])}")
    raw = ask("Nhập số, cách nhau dấu phẩy", "1", input_fn)
    picked = {topics[int(x) - 1]["name"] for x in raw.replace(" ", "").split(",") if x.isdigit()
              and 1 <= int(x) <= len(topics)} or {topics[0]["name"]}
    ov["topics"] = [{**t, "enabled": t["name"] in picked} for t in topics]

    llm = choose("Mô hình AI để dịch & viết hook:", [
        ("anthropic", "Claude (khuyên dùng — văn phong tự nhiên nhất, ước tính ~1–1,5 USD/video 1 tiếng)"),
        ("gemini", "Gemini (rẻ hơn)")], 1, input_fn)
    if llm == "anthropic":
        ov["llm"] = {"provider": "anthropic", "model": "claude-opus-5-5"}
        needed.append("ANTHROPIC_API_KEY")
    else:
        ov["llm"] = {"provider": "gemini", "model": "gemini-2.5-pro"}
        needed.append("GEMINI_API_KEY")

    voice = choose("Giọng đọc:", [
        ("google", "Google Chirp 3 HD — tự nhiên, khác biệt với kênh khác (~1–2 USD/video 1 tiếng) — khuyên dùng"),
        ("edge", "Edge TTS — miễn phí, nhưng giọng HoaiMy/NamMinh đã rất phổ biến"),
        ("elevenlabs", "ElevenLabs — biểu cảm nhất, đắt")], 1, input_fn)
    ov["tts"]["engine"] = voice
    needed.append({"google": "GOOGLE_TTS_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}.get(voice, ""))
    if voice == "elevenlabs":
        ov["tts"]["elevenlabs"] = {"voice_id": ask("voice_id ElevenLabs (xem bằng lệnh `voices`)", "", input_fn)}

    img = choose("Ảnh minh họa thumbnail:", [
        ("cloud", "Google Imagen trên cloud (khuyên dùng, ~1.000đ/ảnh)"),
        ("comfyui", "ComfyUI trên máy (cần card mạnh)"),
        ("placeholder", "Tạm thời chưa vẽ ảnh (nền màu) — chỉ để chạy thử")], 1 if not strong else 2, input_fn)
    ov["thumbnail"]["image_engine"] = img
    if img == "comfyui":
        ov["thumbnail"]["comfyui"] = {"enabled": True}
    if img == "cloud" and "GEMINI_API_KEY" not in needed:
        needed.append("GEMINI_API_KEY")

    if yes("\nDuyệt video qua điện thoại bằng Telegram?", True, input_fn):
        ov["review"]["enabled"] = True
        needed.append("TELEGRAM_BOT_TOKEN")
        chat = ask("Chat ID Telegram (để trống nếu chưa có — lấy sau bằng lệnh /id với bot)", "", input_fn)
        if chat:
            ov["review"]["chat_id"] = chat
    if yes("Tự upload lên YouTube khi bạn bấm Đăng trên điện thoại?", False, input_fn):
        ov["youtube"]["enabled"] = True
        print("  ↳ Cần file OAuth: xem README mục 'Upload YouTube tự động', lưu vào secrets/client_secret.json")

    # ---- khóa API
    env_file = Path(env_path)
    env = read_env(env_file)
    print("\n== Khóa API (gõ ẩn; Enter để bỏ qua / giữ khóa cũ)")
    for key in dict.fromkeys(k for k in needed if k):
        have = env.get(key) or os.environ.get(key)
        print(f"  {key}: {KEY_HELP.get(key, '')}")
        value = secret_fn(f"  Dán {key}{' (đã có — Enter để giữ)' if have else ''}: ").strip()
        if value:
            env[key] = value
    write_env(env_file, env)

    ov = {k: v for k, v in ov.items() if v}
    cfg_file = Path(config_path)
    if cfg_file.exists():
        shutil.copy(cfg_file, cfg_file.with_suffix(".yaml.bak"))
    cfg_file.write_text("# Tạo bởi `python -m autovideo setup` — chỉ chứa lựa chọn của bạn,\n"
                        "# mọi tùy chọn khác xem/ghi đè từ config.example.yaml\n"
                        + yaml.safe_dump(ov, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\n✔ Đã lưu {cfg_file} và {env_file}")
    print("Tiếp theo:\n  1. python scripts/get_fonts.py\n  2. python -m autovideo doctor --online\n"
          "  3. python -m autovideo brand        (xem trước thumbnail/clip của kênh)\n"
          "  4. python -m autovideo auto --dry-run  rồi  python -m autovideo auto")
    return ov
