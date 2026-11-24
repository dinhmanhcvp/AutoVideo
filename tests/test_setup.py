import os

import yaml

from autovideo import config
from autovideo.config import load_config
from autovideo.setup_wizard import run_setup


def test_setup_writes_minimal_config_and_env(tmp_path, monkeypatch):
    answers = iter([
        "Kênh Của Tôi",  # tên kênh
        "2",             # máy yếu
        "1,2",           # chủ đề
        "1",             # Claude
        "1",             # Google TTS
        "1",             # ảnh cloud
        "c", "123456",   # Telegram + chat id
        "k",             # không upload YouTube
    ])
    secrets = iter(["sk-groq", "sk-ant", "g-tts", "g-ai", "tg-token"])
    cfg_path, env_path = tmp_path / "config.yaml", tmp_path / ".env"
    run_setup(str(cfg_path), str(env_path), input_fn=lambda p: next(answers), secret_fn=lambda p: next(secrets))

    env = env_path.read_text(encoding="utf-8")
    for line in ("GROQ_API_KEY=sk-groq", "ANTHROPIC_API_KEY=sk-ant", "GOOGLE_TTS_API_KEY=g-tts",
                 "GEMINI_API_KEY=g-ai", "TELEGRAM_BOT_TOKEN=tg-token"):
        assert line in env
    saved = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert saved["channel"]["name"] == "Kênh Của Tôi" and saved["asr"]["engine"] == "groq"
    cfg = load_config(cfg_path)
    enabled = [t["name"] for t in cfg["topics"] if t.get("enabled", True)]
    assert enabled == ["hai_huoc_gia_dinh", "pha_an_kinh_di"]
    assert cfg["tts"]["engine"] == "google" and cfg["review"]["chat_id"] == "123456"
    assert cfg["hook"]["enabled"] is True  # mặc định vẫn giữ

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    loaded = config.load_env(env_path)
    try:
        assert "GROQ_API_KEY" in loaded and os.environ["GROQ_API_KEY"] == "sk-groq"
    finally:
        for k in loaded:  # chỉ gỡ những biến test vừa nạp
            os.environ.pop(k, None)
