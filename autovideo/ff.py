"""Tiện ích FFmpeg dùng chung."""
from __future__ import annotations

import functools
import json
import subprocess
from pathlib import Path


def run(args: list[str], quiet: bool = True) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-y"]
    if quiet:
        cmd += ["-loglevel", "error", "-stats"]
    cmd += [str(a) for a in args]
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg lỗi ({proc.returncode}):\n{' '.join(cmd)}\n{proc.stderr[-3000:]}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


@functools.lru_cache(maxsize=None)
def encoder_works(name: str) -> bool:
    try:
        run(["-f", "lavfi", "-i", "color=black:s=256x256:d=0.2", "-c:v", name, "-f", "null", "-"])
        return True
    except RuntimeError:
        return False


def pick_encoder(pref: str = "auto") -> str:
    if pref != "auto":
        return pref
    return "h264_nvenc" if encoder_works("h264_nvenc") else "libx264"


def video_codec_args(encoder: str) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", encoder, "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]


def concat_list(paths: list[Path], list_file: Path) -> Path:
    lines = []
    for p in paths:
        escaped = str(Path(p).resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_file
