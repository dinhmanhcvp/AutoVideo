"""Điều phối các module. Mỗi bước ghi file trung gian vào output/<slug>/ và tự bỏ qua nếu đã có
=> chạy lại lệnh sẽ tiếp tục từ chỗ dừng; xóa file của bước nào để làm lại bước đó.

Các bước:
  fetch     tải audio / nhận file .txt (tiếng Trung hoặc tiếng Việt)
  asr       bóc băng tiếng Trung
  analyze   chấm điểm truyện + bảng nhân vật/thuật ngữ (cổng chất lượng)
  translate dịch có QA, metadata (3 tên truyện, chương, mô tả...), hook 2–5 phút
  tts       giọng đọc: hook (theo câu, có phụ đề) + truyện chính
  package   thumbnail 3 phương án, tiêu đề, mô tả có mục lục chương, bình luận ghim
  render    video YouTube + clip TikTok + YouTube Shorts
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path

STAGES = ["fetch", "asr", "analyze", "translate", "tts", "package", "render"]
STAGE_ALIASES = {"thumbnail": "package"}


def slugify(text: str, max_len: int = 48) -> str:
    text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].strip("-")


def job_slug(source: str) -> str:
    stem = Path(source).stem if Path(source).exists() else source
    digest = hashlib.sha1(source.encode()).hexdigest()[:8]
    base = slugify(stem) or "job"
    return f"{base[:32]}-{digest}"


class Job:
    def __init__(self, source: str, cfg: dict, name: str | None = None, strict: bool = False):
        self.source = source
        self.cfg = cfg
        self.strict = strict  # True: truyện không đạt cổng chất lượng thì dừng (chế độ auto)
        self.dir = Path(cfg["workdir"]) / (name or job_slug(source))
        self.dir.mkdir(parents=True, exist_ok=True)
        self._llm = None

    def p(self, name: str) -> Path:
        return self.dir / name

    def read_json(self, name: str, default=None):
        path = self.p(name)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def write_json(self, name: str, data) -> None:
        self.p(name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    @property
    def llm(self):
        if self._llm is None:
            from .llm import make_llm

            self._llm = make_llm(self.cfg["llm"])
        return self._llm

    def save_cost(self, stage: str):
        usage = getattr(self._llm, "usage", None)
        if usage is None:
            return
        cost = self.read_json("cost.json", {})
        cost[stage] = usage.snapshot()
        cost["total_usd"] = round(sum(v["usd"] for k, v in cost.items() if isinstance(v, dict)), 4)
        self.write_json("cost.json", cost)

    # ------------------------------------------------------------ fetch / asr

    def fetch(self):
        src = Path(self.source)
        if src.exists():
            if src.suffix.lower() in {".txt", ".md"}:
                from .analyze import detect_language

                text = src.read_text(encoding="utf-8")
                # File tiếng Việt có sẵn (bạn tự sưu tầm) => bỏ qua bóc băng và dịch
                target = "story_vi.txt" if detect_language(text) == "vi" else "source_zh.txt"
                self.p(target).write_text(text, encoding="utf-8")
            else:
                shutil.copy(src, self.p("source" + src.suffix.lower()))
            return
        if self.p("source.m4a").exists():
            return
        from .fetch import download_audio

        _, meta = download_audio(self.source, self.dir, self.cfg["source"].get("cookies_file"))
        self.write_json("source_info.json", meta)

    def asr(self):
        if self.p("source_zh.txt").exists() or self.p("story_vi.txt").exists():
            return
        audio = next((p for p in sorted(self.dir.glob("source.*")) if p.suffix not in {".json", ".txt"}), None)
        if audio is None:
            raise FileNotFoundError(f"Chưa có audio nguồn trong {self.dir}")
        from .asr import transcribe

        text = transcribe(audio, self.p("transcript_zh.json"), self.cfg["asr"])
        self.p("source_zh.txt").write_text(text, encoding="utf-8")

    # ------------------------------------------------------------ analyze (cổng chất lượng)

    def source_text(self) -> str:
        for name in ("source_zh.txt", "story_vi.txt"):
            if self.p(name).exists():
                return self.p(name).read_text(encoding="utf-8")
        raise FileNotFoundError(f"Chưa có văn bản truyện trong {self.dir}")

    def analyze(self):
        from .analyze import StoryRejected, analyze, verdict

        if not self.cfg.get("quality", {}).get("enabled", True):
            return
        report = self.read_json("analysis.json")
        if report is None:
            report = analyze(self.llm, self.source_text(), self.cfg)
            report["verdict"] = verdict(report, self.cfg)
            self.write_json("analysis.json", report)
            self.save_cost("analyze")
        s = report.get("scores", {})
        print(f"  [đánh giá] điểm {report['score']} (hook {s.get('hook')}, twist {s.get('twist')}, "
              f"cảm xúc {s.get('emotion')}) · trọn vẹn: {report.get('complete')} · {report.get('logline_vi', '')}")
        if report.get("verdict"):
            msg = f"Truyện không đạt: {report['verdict']}"
            if self.strict:
                raise StoryRejected(msg)
            print(f"  [đánh giá] ⚠ {msg} — vẫn tiếp tục vì bạn chạy thủ công")

    # ------------------------------------------------------------ translate + metadata + hook

    def translate(self):
        from .analyze import character_notes, story_glossary
        from .translate import compose_script, make_metadata, translate

        report = self.read_json("analysis.json", {})
        if not self.p("story_vi.txt").exists():
            zh = self.p("source_zh.txt").read_text(encoding="utf-8")
            vi = translate(self.llm, zh, self.cfg, progress_file=self.p("translate_progress.json"),
                           extra_glossary=story_glossary(report), characters=character_notes(report),
                           qa_file=self.p("translate_qa.json"))
            self.p("story_vi.txt").write_text(vi, encoding="utf-8")
            self.save_cost("translate")
        vi = self.p("story_vi.txt").read_text(encoding="utf-8")
        if not self.p("metadata.json").exists():
            self.write_json("metadata.json", make_metadata(self.llm, vi, self.cfg))
            self.save_cost("metadata")
        meta = self.read_json("metadata.json")
        if self.cfg.get("hook", {}).get("enabled") and not self.p("hook.json").exists():
            from .hook import make_hook

            data = make_hook(self.llm, vi, meta, self.cfg)
            self.write_json("hook.json", data)
            self.p("tiktok_caption.txt").write_text(data.get("tiktok_caption", ""), encoding="utf-8")
            self.save_cost("hook")
        if not self.p("script_vi.txt").exists():
            bridge = self.read_json("hook.json", {}).get("bridge", "")
            self.p("script_vi.txt").write_text(compose_script(vi, meta, bridge), encoding="utf-8")

    # ------------------------------------------------------------ tts

    def tts(self):
        if self.p("voice.wav").exists():
            return
        from . import ff
        from .tts import concat_wavs, silence, synth_pieces, synthesize, synthesize_timed

        tcfg = self.cfg["tts"]
        script = self.p("script_vi.txt").read_text(encoding="utf-8")
        hook = self.read_json("hook.json")
        if not hook:
            synthesize(script, self.dir, tcfg)
            return
        from .hook import check_length

        hook_wav, _ = synthesize_timed(hook["hook"], self.dir, tcfg, "hook")
        if warn := check_length(ff.duration(hook_wav), self.cfg):
            print(f"  [hook] ⚠ {warn}")
            hook["warning"] = warn
            self.write_json("hook.json", hook)
        for key, sub in (("tiktok_cta", "cta"), ("shorts_cta", "cta_shorts")):
            if hook.get(key):
                synth_pieces([hook[key]], self.dir / "tts" / sub, tcfg)
        main = synthesize(script, self.dir, tcfg, out_name="main.wav")
        # Video YouTube: hook -> ngắt 1 giây -> câu chuyển + lời dẫn + truyện + lời bình
        concat_wavs([hook_wav, silence(self.dir / "tts" / "pause_1s.wav", 1.0), main],
                    self.p("voice.wav"), self.dir / "tts" / "voice_list.txt")

    # ------------------------------------------------------------ package

    def next_episode(self) -> int:
        counter = Path(self.cfg["workdir"]) / "episode_counter.txt"
        n = int(counter.read_text()) + 1 if counter.exists() else int(self.cfg["channel"].get("episode_start", 1))
        counter.write_text(str(n))
        return n

    def thumbnail_cfg(self, meta: dict) -> dict:
        tcfg = dict(self.cfg["thumbnail"])
        tcfg["badge"] = (tcfg.get("badge") or "").replace("{channel_name}", self.cfg["channel"]["name"]) \
                                                .replace("{episode}", str(meta.get("episode", "")))
        return tcfg

    def package(self):
        from .package import chapters, description, render_variants
        from .thumbnail import make_background
        from .translate import final_title

        meta = self.read_json("metadata.json")
        uses_episode = "{episode}" in (self.cfg["thumbnail"].get("badge") or "") + \
                       (self.cfg["channel"].get("title_template") or "")
        if uses_episode and "episode" not in meta:
            meta["episode"] = self.next_episode()
        meta["youtube_title"] = final_title(meta, self.cfg)
        # Tiêu đề hoàn chỉnh của cả 3 phương án (để chọn trên điện thoại)
        meta["titles"] = [final_title({**meta, "story_title": v["story_title"]}, self.cfg)
                          for v in meta.get("title_variants", [])] or [meta["youtube_title"]]
        self.write_json("metadata.json", meta)

        tcfg = self.thumbnail_cfg(meta)
        bg = self.p("thumb_bg.png")
        if not bg.exists():
            make_background(meta["image_prompt"], bg, tcfg)
        render_variants(bg, meta, self.dir, tcfg)

        if self.p("tts/chunks.json").exists():
            marks = chapters(meta, self.dir, self.cfg)
            playlist = (self.cfg.get("youtube", {}).get("playlists") or {}).get(self.cfg.get("_topic", ""))
            self.p("youtube_description.txt").write_text(description(meta, self.cfg, marks, playlist),
                                                         encoding="utf-8")
        self.p("pinned_comment.txt").write_text(meta.get("pinned_comment", ""), encoding="utf-8")

        if self.cfg["render"]["mode"] == "still":
            scenes_dir = self.p("scenes")
            scenes_dir.mkdir(exist_ok=True)
            prompts = meta["scene_prompts"][: self.cfg["render"]["still"]["scenes"]]
            for i, prompt in enumerate(prompts):
                out = scenes_dir / f"{i:02d}.png"
                if not out.exists():
                    if i == 0:
                        shutil.copy(bg, out)  # cảnh 1 = ảnh nền thumbnail (đồng bộ với thứ người xem vừa bấm)
                    else:
                        make_background(prompt, out, tcfg)
                    print(f"  [ảnh] cảnh {i + 1}/{len(prompts)}")

    thumbnail = package  # tên cũ

    # ------------------------------------------------------------ render

    def render(self):
        if not self.p("video.mp4").exists():
            from .render import render

            mode = self.cfg["render"]["mode"]
            if mode == "thumbnail":
                images = [self.p("thumbnail.jpg")]
            else:
                images = sorted(self.p("scenes").glob("*.png")) if self.p("scenes").exists() else []
            if not images:
                images = [self.p("thumb_bg.png")]
            render(self.p("voice.wav"), images, self.dir, self.cfg["render"])
        self.render_vertical()

    def render_vertical(self):
        """Clip TikTok (hook đầy đủ) + YouTube Shorts (hook cắt ≤ shorts.max_seconds)."""
        hook = self.read_json("hook.json")
        if not hook or not self.p("hook_captions.json").exists():
            return
        from .hook import render_short, render_tiktok

        meta = self.read_json("metadata.json")
        if self.cfg.get("tiktok", {}).get("enabled") and not self.p("tiktok.mp4").exists():
            cta = self.dir / "tts" / "cta" / "0000.norm.wav"
            captions = self.read_json("hook_captions.json")
            render_tiktok(self.dir, meta, self.p("hook.wav"), captions, cta if cta.exists() else None, self.cfg)
            print(f"  [tiktok] ✔ {self.p('tiktok.mp4')}")
        if self.cfg.get("shorts", {}).get("enabled") and not self.p("short.mp4").exists():
            render_short(self, meta)
            print(f"  [shorts] ✔ {self.p('short.mp4')}")

    render_tiktok = render_vertical  # tên cũ

    # ------------------------------------------------------------ chạy

    def run(self, stages: list[str] | None = None):
        for stage in stages or STAGES:
            stage = STAGE_ALIASES.get(stage, stage)
            print(f"[{self.dir.name}] ▶ {stage}")
            getattr(self, stage)()
        cost = self.read_json("cost.json", {})
        extra = f" · chi phí LLM ~${cost['total_usd']}" if cost.get("total_usd") else ""
        print(f"[{self.dir.name}] ✔ xong: {self.dir}{extra}")
