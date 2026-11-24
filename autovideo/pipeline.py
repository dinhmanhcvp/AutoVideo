"""Điều phối các module. Mỗi bước ghi file trung gian vào output/<slug>/ và tự bỏ qua nếu đã có
=> chạy lại lệnh sẽ tiếp tục từ chỗ dừng; xóa file của bước nào để làm lại bước đó."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path



STAGES = ["fetch", "asr", "translate", "tts", "thumbnail", "render"]


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
    def __init__(self, source: str, cfg: dict, name: str | None = None):
        self.source = source
        self.cfg = cfg
        self.dir = Path(cfg["workdir"]) / (name or job_slug(source))
        self.dir.mkdir(parents=True, exist_ok=True)
        self._llm = None

    def p(self, name: str) -> Path:
        return self.dir / name

    @property
    def llm(self):
        if self._llm is None:
            from .llm import make_llm

            self._llm = make_llm(self.cfg["llm"])
        return self._llm

    # ------------------------------------------------------------ stages

    def fetch(self):
        src = Path(self.source)
        if src.exists():
            if src.suffix.lower() in {".txt", ".md"}:  # đã có text tiếng Trung — bỏ qua ASR
                shutil.copy(src, self.p("source_zh.txt"))
            else:
                shutil.copy(src, self.p("source" + src.suffix.lower()))
            return
        if self.p("source.m4a").exists():
            return
        from .fetch import download_audio

        _, meta = download_audio(self.source, self.dir, self.cfg["source"].get("cookies_file"))
        self.p("source_info.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def asr(self):
        if self.p("source_zh.txt").exists():
            return
        audio = next((p for p in sorted(self.dir.glob("source.*")) if p.suffix not in {".json", ".txt"}), None)
        if audio is None:
            raise FileNotFoundError(f"Chưa có audio nguồn trong {self.dir}")
        from .asr import transcribe

        text = transcribe(audio, self.p("transcript_zh.json"), self.cfg["asr"])
        self.p("source_zh.txt").write_text(text, encoding="utf-8")

    def translate(self):
        from .translate import compose_script, make_metadata, translate

        if not self.p("story_vi.txt").exists():
            zh = self.p("source_zh.txt").read_text(encoding="utf-8")
            vi = translate(self.llm, zh, self.cfg, progress_file=self.p("translate_progress.json"))
            self.p("story_vi.txt").write_text(vi, encoding="utf-8")
        vi = self.p("story_vi.txt").read_text(encoding="utf-8")
        if not self.p("metadata.json").exists():
            meta = make_metadata(self.llm, vi, self.cfg)
            self.p("metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            desc = meta["description"] + "\n\n" + " ".join("#" + t.replace(" ", "") for t in meta["tags"][:5])
            self.p("youtube_description.txt").write_text(desc, encoding="utf-8")
        meta = json.loads(self.p("metadata.json").read_text(encoding="utf-8"))
        hook = self.cfg.get("hook", {})
        if hook.get("enabled") and not self.p("hook.json").exists():
            from .hook import make_hook

            data = make_hook(self.llm, vi, meta, self.cfg)
            self.p("hook.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            self.p("tiktok_caption.txt").write_text(data.get("tiktok_caption", ""), encoding="utf-8")
        if not self.p("script_vi.txt").exists():
            bridge = ""
            if self.p("hook.json").exists():
                bridge = json.loads(self.p("hook.json").read_text(encoding="utf-8")).get("bridge", "")
            self.p("script_vi.txt").write_text(compose_script(vi, meta, bridge), encoding="utf-8")

    def tts(self):
        if self.p("voice.wav").exists():
            return
        from . import ff
        from .tts import concat_wavs, silence, synth_pieces, synthesize, synthesize_timed

        tcfg = self.cfg["tts"]
        script = self.p("script_vi.txt").read_text(encoding="utf-8")
        if not self.p("hook.json").exists():
            synthesize(script, self.dir, tcfg)
            return
        from .hook import check_length

        hook = json.loads(self.p("hook.json").read_text(encoding="utf-8"))
        hook_wav, _ = synthesize_timed(hook["hook"], self.dir, tcfg, "hook")
        if warn := check_length(ff.duration(hook_wav), self.cfg):
            print(f"  [hook] ⚠ {warn}")
            hook["warning"] = warn
            self.p("hook.json").write_text(json.dumps(hook, ensure_ascii=False, indent=1), encoding="utf-8")
        if hook.get("tiktok_cta"):
            synth_pieces([hook["tiktok_cta"]], self.dir / "tts" / "cta", tcfg)
        main = synthesize(script, self.dir, tcfg, out_name="main.wav")
        # Video YouTube: hook -> ngắt 1 giây -> câu chuyển + lời dẫn + truyện + lời bình
        concat_wavs([hook_wav, silence(self.dir / "tts" / "pause_1s.wav", 1.0), main],
                    self.p("voice.wav"), self.dir / "tts" / "voice_list.txt")

    def next_episode(self) -> int:
        counter = Path(self.cfg["workdir"]) / "episode_counter.txt"
        n = int(counter.read_text()) + 1 if counter.exists() else int(self.cfg["channel"].get("episode_start", 1))
        counter.write_text(str(n))
        return n

    def thumbnail(self):
        from .thumbnail import make_background, render_thumbnail
        from .translate import final_title

        meta = json.loads(self.p("metadata.json").read_text(encoding="utf-8"))
        tcfg = dict(self.cfg["thumbnail"])
        uses_episode = "{episode}" in (tcfg.get("badge") or "") + (self.cfg["channel"].get("title_template") or "")
        if uses_episode and "episode" not in meta:
            meta["episode"] = self.next_episode()
        meta["youtube_title"] = final_title(meta, self.cfg)
        self.p("metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tcfg["badge"] = (tcfg.get("badge") or "").replace("{channel_name}", self.cfg["channel"]["name"]) \
                                                .replace("{episode}", str(meta.get("episode", "")))
        bg = self.p("thumb_bg.png")
        if not bg.exists():
            make_background(meta["image_prompt"], bg, tcfg)
        if not self.p("thumbnail.jpg").exists():
            render_thumbnail(bg, meta, self.p("thumbnail.jpg"), tcfg)

        if self.cfg["render"]["mode"] == "still":
            scenes_dir = self.p("scenes")
            scenes_dir.mkdir(exist_ok=True)
            prompts = meta["scene_prompts"][: self.cfg["render"]["still"]["scenes"]]
            for i, prompt in enumerate(prompts):
                out = scenes_dir / f"{i:02d}.png"
                if not out.exists():
                    if i == 0 and len(prompts) == 1:
                        shutil.copy(bg, out)  # 1 cảnh: dùng luôn ảnh nền thumbnail (bản chưa chèn chữ)
                    else:
                        make_background(prompt, out, tcfg)
                    print(f"  [ảnh] cảnh {i + 1}/{len(prompts)}")

    def render(self):
        if self.p("video.mp4").exists():
            self.render_tiktok()
            return
        from .render import render

        mode = self.cfg["render"]["mode"]
        if mode == "thumbnail":
            images = [self.p("thumbnail.jpg")]
        else:
            images = sorted(self.p("scenes").glob("*.png")) if self.p("scenes").exists() else []
        if not images:
            images = [self.p("thumb_bg.png")]
        render(self.p("voice.wav"), images, self.dir, self.cfg["render"])
        self.render_tiktok()

    def render_tiktok(self):
        if not (self.cfg.get("tiktok", {}).get("enabled") and self.p("hook.json").exists()):
            return
        if self.p("tiktok.mp4").exists():
            return
        from .hook import render_tiktok

        meta = json.loads(self.p("metadata.json").read_text(encoding="utf-8"))
        captions = json.loads(self.p("hook_captions.json").read_text(encoding="utf-8"))
        cta = self.dir / "tts" / "cta" / "0000.norm.wav"
        render_tiktok(self.dir, meta, self.p("hook.wav"), captions, cta if cta.exists() else None, self.cfg)
        print(f"  [tiktok] ✔ {self.p('tiktok.mp4')}")

    def run(self, stages: list[str] | None = None):
        for stage in stages or STAGES:
            print(f"[{self.dir.name}] ▶ {stage}")
            getattr(self, stage)()
        print(f"[{self.dir.name}] ✔ xong: {self.dir}")
