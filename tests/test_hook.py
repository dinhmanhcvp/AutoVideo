"""Hook + TikTok: TTS giả bằng FFmpeg (độ dài theo số chữ) để kiểm tra mốc thời gian phụ đề."""
import json
import sys

from PIL import Image

from autovideo import ff, hook, tts
from autovideo.config import load_config
from autovideo.pipeline import Job
from autovideo.thumbnail import placeholder_background

# TTS giả: mỗi chữ 0.1 giây -> biết trước độ dài từng câu
FAKE_TTS = (f'"{sys.executable}" -c "import sys,subprocess;t=open(sys.argv[1],encoding=\'utf-8\').read();'
            'subprocess.run([\'ffmpeg\',\'-y\',\'-loglevel\',\'error\',\'-f\',\'lavfi\',\'-i\',\'sine=frequency=300\','
            '\'-t\',str(0.1*len(t.split())),sys.argv[2]],check=True)" {text_file} {out}')


def tts_cfg():
    return dict(load_config()["tts"], engine="command", command=FAKE_TTS)


def test_caption_units_split_long_sentence():
    s = " ".join(f"từ{i}" for i in range(30))
    units = tts.caption_units(s, 12)
    assert all(len(u.split()) <= 14 for u in units) and " ".join(units) == s


def test_synthesize_timed_captions_match_audio(tmp_path):
    text = "Một hai ba bốn năm. " + " ".join(["chữ"] * 20) + ". Hết."
    wav, caps = tts.synthesize_timed(text, tmp_path, tts_cfg(), "hook", gap=0.25)
    assert abs(caps[0]["end"] - 0.5) < 0.05          # câu 1: 5 chữ = 0.5s
    assert abs(caps[1]["start"] - 0.75) < 0.05       # + khoảng nghỉ 0.25s
    assert abs(caps[-1]["end"] - (0.5 + 0.25 + 2.0 + 0.25 + 0.1)) < 0.05
    assert abs(ff.duration(wav) - caps[-1]["end"] - 0.25) < 0.1


def test_hook_length_warning():
    cfg = load_config()
    assert hook.check_length(180, cfg) is None
    assert "ngoài khoảng" in hook.check_length(30, cfg)


def test_tiktok_render_vertical_with_captions(tmp_path):
    cfg = load_config(overrides={"render": {"audio": {"music_dir": str(tmp_path / "none")}}})
    placeholder_background("x", tmp_path / "thumb_bg.png")
    wav, caps = tts.synthesize_timed("Ngày cưới, tôi phát hiện chồng sắp cưới đã chết. Ba năm trước.",
                                     tmp_path, tts_cfg(), "hook")
    cta = tts.synth_pieces(["Nghe tiếp trên YouTube nhé."], tmp_path / "cta", tts_cfg())[0]
    meta = {"story_title": "Chiếc Túi Da Người Và Lời Nói Dối 18 Năm", "thumb_highlight": ["18 Năm"], "episode": 7}
    out = hook.render_tiktok(tmp_path, meta, wav, caps, cta, cfg)
    total = 0.2 + ff.duration(wav) + 0.6 + ff.duration(cta) + 1.5
    assert abs(ff.duration(out) - total) < 0.3
    frame = tmp_path / "f.png"
    ff.run(["-ss", "0.5", "-i", out, "-frames:v", 1, frame])
    im = Image.open(frame)
    assert im.size == (1080, 1920)
    # Ở giây 0.5 phải có phụ đề (chữ trắng) trong vùng phụ đề
    region = im.convert("L").crop((70, 1100, 950, 1390))
    assert region.getextrema()[1] > 240


def test_job_tts_puts_hook_first(tmp_path):
    cfg = load_config(overrides={"workdir": str(tmp_path)})
    cfg["tts"] = tts_cfg()
    job = Job("x", cfg, name="x")
    job.p("hook.json").write_text(json.dumps({"hook": "Câu hook một. Câu hai.", "tiktok_cta": "Mời nghe."}),
                                  encoding="utf-8")
    job.p("script_vi.txt").write_text("Truyện chính dài dài.", encoding="utf-8")
    job.tts()
    assert abs(ff.duration(job.p("voice.wav")) - (ff.duration(job.p("hook.wav")) + 1.0 + ff.duration(job.p("main.wav")))) < 0.1
    assert job.p("tts/cta/0000.norm.wav").exists()
