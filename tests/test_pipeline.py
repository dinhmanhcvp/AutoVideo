"""Test offline: không gọi mạng / LLM / GPU. LLM được giả lập, TTS dùng tone sinh bằng FFmpeg."""
import json
import random
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from autovideo import ff, render, thumbnail
from autovideo.config import load_config
from autovideo.llm import extract_json
from autovideo.translate import compose_script, normalize_metadata, split_for_tts, split_source, translate


def lavfi(out: Path, src: str, dur: float, extra=()):
    ff.run(["-f", "lavfi", "-i", src, "-t", dur, *extra, out])
    return out


def test_split_source_respects_limit():
    text = "第一句话。" * 50 + "\n" + "很长没有标点" * 40
    chunks = split_source(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_for_tts_sentence_boundaries():
    text = " ".join(["Đây là một câu thử nghiệm có tám chữ."] * 100)
    chunks = split_for_tts(text, 250)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 250 for c in chunks)
    assert all(c.endswith(".") for c in chunks)


def test_extract_json_variants():
    assert extract_json('Đây:\n```json\n{"a": 1}\n```')["a"] == 1
    assert extract_json('ok {"a": {"b": [1, 2]}} thừa')["a"]["b"] == [1, 2]


def test_normalize_metadata_splits_thumb_text():
    cfg = load_config()
    meta = normalize_metadata({"thumb_text": "Sư Tôn Đừng Bỏ Ta", "image_prompt": "a hall"}, cfg)
    assert meta["thumb_text"] == ["Sư Tôn Đừng", "Bỏ Ta"]
    assert cfg["channel"]["visual_style"] in meta["image_prompt"]
    assert compose_script("truyện", {"intro": "mở", "outro": "kết"}) == "mở\n\ntruyện\n\nkết"


class FakeLLM:
    def __init__(self):
        self.calls = []

    def complete(self, system, user, max_tokens=0):
        self.calls.append(user)
        return f"Bản dịch số {len(self.calls)}."


def test_translate_passes_previous_context_and_resumes(tmp_path):
    cfg = load_config(overrides={"llm": {"source_chunk_chars": 10}})
    llm = FakeLLM()
    progress = tmp_path / "p.json"
    out = translate(llm, "一二三四五。六七八九十。甲乙丙丁戊。", cfg, progress_file=progress)
    assert out.count("Bản dịch") == 3
    assert "Bản dịch số 1." in llm.calls[1]  # ngữ cảnh đoạn trước được gửi kèm
    llm2 = FakeLLM()
    translate(llm2, "一二三四五。六七八九十。甲乙丙丁戊。", cfg, progress_file=progress)
    assert llm2.calls == []  # đã xong hết => không gọi lại


def test_plan_sequence_no_adjacent_repeat():
    durs = {Path(f"{i}.mp4"): 5.0 for i in range(4)}
    seq = render.plan_sequence(durs, 200, random.Random(1))
    assert sum(durs[c] for c in seq) >= 200
    assert all(a != b for a, b in zip(seq, seq[1:]))


def test_thumbnail_compose(tmp_path):
    bg = thumbnail.placeholder_background("a misty mountain temple", tmp_path / "bg.png")
    cfg = load_config()["thumbnail"]
    out = thumbnail.compose(bg, ["Sư Tôn", "Đừng Bỏ Ta"], tmp_path / "t.jpg", cfg)
    assert Image.open(out).size == (1280, 720)


@pytest.fixture
def media(tmp_path):
    voice = lavfi(tmp_path / "voice.wav", "sine=frequency=300:sample_rate=44100", 6, ["-ac", "1"])
    music = tmp_path / "music"
    music.mkdir()
    lavfi(music / "a.mp3", "sine=frequency=600", 3)
    lavfi(music / "b.mp3", "sine=frequency=800", 4)
    foot = tmp_path / "footage" / "warm"
    foot.mkdir(parents=True)
    lavfi(foot / "c1.mp4", "testsrc=size=640x360:rate=25", 2)
    lavfi(foot / "c2.mp4", "testsrc2=size=1280x720:rate=30", 3)
    return tmp_path, voice, music, foot.parent


def _rcfg(tmp, music, foot, mode, ducking="sidechain"):
    cfg = load_config(overrides={"render": {
        "mode": mode, "resolution": [320, 180], "fps": 15, "encoder": "libx264", "lead_in": 1, "tail": 1,
        "footage": {"dir": str(foot), "tone": "warm", "seed": 3},
        "still": {"scenes": 2, "zoom_period": 4},
        "audio": {"music_dir": str(music), "ducking": ducking},
    }})
    return cfg["render"]


@pytest.mark.parametrize("mode,ducking", [("footage", "sidechain"), ("still", "fixed")])
def test_render_end_to_end(media, mode, ducking):
    tmp, voice, music, foot = media
    imgs = [thumbnail.placeholder_background(f"scene {i}", tmp / f"s{i}.png", size=(640, 360)) for i in range(2)]
    work = tmp / f"job_{mode}"
    work.mkdir()
    out = render.render(voice, imgs, work, _rcfg(tmp, music, foot, mode, ducking))
    assert abs(ff.duration(out) - 8.0) < 0.5
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width",
                              "-of", "json", str(out)], capture_output=True, text=True).stdout
    kinds = {s["codec_type"]: s for s in json.loads(streams)["streams"]}
    assert kinds["video"]["width"] == 320 and "audio" in kinds


def test_still_with_overlay(media):
    tmp, voice, music, foot = media
    overlay = tmp / "dust.mp4"
    ff.run(["-f", "lavfi", "-i", "color=black:s=320x180:r=15", "-vf", "noise=alls=60:allf=t", "-t", 1, overlay])
    rcfg = _rcfg(tmp, music, foot, "still")
    rcfg["still"]["overlay"] = str(overlay)
    img = thumbnail.placeholder_background("x", tmp / "x.png", size=(640, 360))
    out = render.still_track([img], 3, tmp / "bg.mp4", rcfg, "libx264")
    assert abs(ff.duration(out) - 3) < 0.3
