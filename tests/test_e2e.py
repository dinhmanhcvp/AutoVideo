"""End-to-end: chạy đủ 7 bước (fetch → asr → analyze → translate → tts → package → render) + export,
với LLM giả (trả lời theo loại nhiệm vụ) và TTS giả bằng FFmpeg. Không cần mạng/GPU."""
import json
import sys
from pathlib import Path

import pytest

from autovideo import auto, ff
from autovideo.analyze import StoryRejected
from autovideo.config import load_config
from autovideo.llm import Usage
from autovideo.pipeline import Job

sys.path.insert(0, str(Path(__file__).parent))
from test_hook import FAKE_TTS  # noqa: E402

ZH = "\n".join(f"第{i}段。" + "她推开门，看见了那个本该死去三年的人。" * 12 for i in range(1, 5))


class ScriptedLLM:
    """Trả lời đúng định dạng cho từng loại nhiệm vụ, giống LLM thật."""

    def __init__(self, scores=None):
        self.usage = Usage("claude-opus-5-5")
        self.scores = scores or {"hook": 9, "premise": 8, "twist": 8, "emotion": 8, "pacing": 7, "vn_fit": 8}
        self.n_translate = 0
        self.docs = []

    def complete(self, system, user, max_tokens=0, doc=None):
        self.usage.add(input_tokens=1000, output_tokens=500, cache_read_input_tokens=800 if doc else 0)
        if doc:
            self.docs.append(doc)
        if "trưởng nhóm nội dung" in system:
            return json.dumps({"complete": True, "language": "zh", "scores": self.scores, "ad_safe": True,
                               "red_flags": [], "logline_vi": "Cô dâu gặp lại người đã chết.",
                               "characters": [{"zh": "林晓", "vi": "Lâm Hiểu", "gender": "nữ"}],
                               "glossary": {}, "pronoun_notes": "tôi – anh"})
        if "Dịch đoạn" in user:
            self.n_translate += 1
            i = self.n_translate
            body = " ".join(["Tôi đẩy cửa bước vào và nhìn thấy người lẽ ra đã chết ba năm trước."] * 10)
            return f"Mốc {i} mở đầu đoạn này. {body}"
        if "title_variants" in system:
            return json.dumps({
                "title_variants": [
                    {"story_title": "Ngày Cưới Tôi Gặp Lại Người Đã Chết Ba Năm", "thumb_highlight": ["Đã Chết"]},
                    {"story_title": "Chú Rể Là Người Đã Chết", "thumb_highlight": ["Đã Chết"]},
                    {"story_title": "Bí Mật Sau Cánh Cửa Phòng Cưới", "thumb_highlight": ["Bí Mật"]},
                ],
                "description": "Điều gì đang chờ sau cánh cửa?", "hashtags": ["#truyenaudio", "truyen hay"],
                "tags": ["truyện audio"], "pinned_comment": "Nếu là bạn, bạn có mở cửa không?",
                "chapters": [{"title": "Mở đầu", "first_words": "Mốc 1 mở đầu đoạn này"},
                             {"title": "Cánh cửa", "first_words": "Mốc 2 mở đầu đoạn này"},
                             {"title": "Sự thật", "first_words": "Mốc 4 mở đầu đoạn này"}],
                "image_prompt": "a bride at a door", "scene_prompts": ["a", "b"],
                "intro": "Chào mừng bạn đến với kênh.", "outro": "Hẹn gặp lại.",
            })
        if '"hook"' in system:
            return json.dumps({"hook": "Ngày cưới, tôi thấy chồng mình đã chết. Anh ấy mỉm cười với tôi. "
                                       "Tại sao anh còn sống? Tôi lùi lại một bước. Ai đã nói dối tôi suốt ba năm?",
                               "bridge": "Để hiểu chuyện này, phải quay lại từ đầu.",
                               "tiktok_cta": "Nghe trọn bộ trên YouTube nhé.", "shorts_cta": "Bấm video liên quan.",
                               "tiktok_caption": "Chú rể đã chết? #truyenaudio"})
        raise AssertionError(f"Nhiệm vụ lạ: {system[:80]}")


def e2e_cfg(tmp_path, **over):
    cfg = load_config(overrides={
        "workdir": str(tmp_path / "out"),
        "llm": {"source_chunk_chars": 300},
        "quality": {"min_chars": 100},
        "tts": {"engine": "command", "command": FAKE_TTS, "gap_ms": 200},
        "thumbnail": {"image_engine": "placeholder"},
        "render": {"mode": "thumbnail", "resolution": [320, 180], "fps": 12, "encoder": "libx264",
                   "x264_preset": "ultrafast", "audio": {"music_dir": str(tmp_path / "nomusic")}},
        "shorts": {"enabled": True, "max_seconds": 4.5},
        "auto": {"ready_dir": str(tmp_path / "ready")},
        **over,
    })
    return cfg


def test_full_pipeline_to_ready_folder(tmp_path):
    src = tmp_path / "truyen.txt"
    src.write_text(ZH, encoding="utf-8")
    cfg = e2e_cfg(tmp_path)
    job = Job(str(src), cfg, strict=True)
    llm = ScriptedLLM()
    job._llm = llm
    job.run()

    # Cổng chất lượng + bảng nhân vật
    analysis = job.read_json("analysis.json")
    assert analysis["score"] >= 8 and analysis["verdict"] is None
    # Dịch: đủ 4 đoạn, có QA log, nhân vật đưa vào prompt
    assert llm.n_translate == 4
    assert job.p("story_vi.txt").read_text(encoding="utf-8").count("Mốc") == 4
    # Prompt caching: cùng 1 khối truyện tiếng Việt được dùng lại cho metadata + hook
    assert len(set(llm.docs[1:])) == 1 and len(llm.docs) == 3
    # Đóng gói
    meta = job.read_json("metadata.json")
    assert len(meta["titles"]) == 3 and meta["titles"][0].startswith("[Truyện Audio] Ngày Cưới")
    for name in ("thumbnail.jpg", "thumbnail_2.jpg", "thumbnail_3.jpg"):
        assert job.p(name).exists()
    desc = job.p("youtube_description.txt").read_text(encoding="utf-8")
    assert "MỤC LỤC" in desc and "00:00 Mở đầu" in desc and "Sự thật" in desc
    assert desc.rstrip().endswith("#truyenaudio #truyenhay")
    assert job.p("pinned_comment.txt").read_text(encoding="utf-8").startswith("Nếu là bạn")
    # Video YouTube = hook + 1s + truyện chính
    hook_d, main_d = ff.duration(job.p("hook.wav")), ff.duration(job.p("main.wav"))
    expected = cfg["render"]["lead_in"] + hook_d + 1.0 + main_d + cfg["render"]["tail"]
    assert abs(ff.duration(job.p("video.mp4")) - expected) < 0.5
    # Kịch bản chính bắt đầu bằng câu chuyển từ hook
    assert job.p("script_vi.txt").read_text(encoding="utf-8").startswith("Để hiểu chuyện này")
    # Clip dọc
    tiktok, short = ff.duration(job.p("tiktok.mp4")), ff.duration(job.p("short.mp4"))
    assert short <= 4.5 + 0.3 < tiktok
    # Chi phí
    cost = job.read_json("cost.json")
    assert cost["total_usd"] > 0 and {"analyze", "translate", "metadata", "hook"} <= set(cost)

    dest = auto.export(job, Path(cfg["auto"]["ready_dir"]))
    for name in ("video.mp4", "tiktok.mp4", "short.mp4", "thumbnail.jpg", "thumbnail_3.jpg", "title.txt",
                 "titles.json", "description.txt", "tags.txt", "pinned_comment.txt", "tiktok_caption.txt",
                 "analysis.json", "cost.json"):
        assert (dest / name).exists(), name


def test_weak_story_rejected_before_translation(tmp_path):
    src = tmp_path / "yeu.txt"
    src.write_text(ZH, encoding="utf-8")
    job = Job(str(src), e2e_cfg(tmp_path), strict=True)
    llm = ScriptedLLM(scores={k: 4 for k in ("hook", "premise", "twist", "emotion", "pacing", "vn_fit")})
    job._llm = llm
    with pytest.raises(StoryRejected):
        job.run()
    assert llm.n_translate == 0 and not job.p("story_vi.txt").exists()


def test_vietnamese_text_skips_translation(tmp_path):
    src = tmp_path / "viet.txt"
    src.write_text("Mốc 1 mở đầu đoạn này. Tôi đẩy cửa bước vào và nhìn thấy người lẽ ra đã chết. " * 20,
                   encoding="utf-8")
    job = Job(str(src), e2e_cfg(tmp_path), strict=True)
    job._llm = ScriptedLLM()
    job.run(["fetch", "asr", "analyze", "translate"])
    assert job._llm.n_translate == 0 and job.p("metadata.json").exists() and job.p("hook.json").exists()
