"""Module 5: dựng track hình (footage / ảnh tĩnh Ken Burns), trộn âm thanh có ducking, mux."""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from . import ff

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}


def _files(folder: Path, exts: set[str]) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in exts and not p.name.startswith("."))


# ---------------------------------------------------------------- Chế độ 1: footage

def _normalize_clip(src: Path, cache: Path, rcfg: dict, encoder: str) -> Path:
    W, H = rcfg["resolution"]
    fcfg = rcfg["footage"]
    key = f"{src.resolve()}|{src.stat().st_mtime}|{W}x{H}|{rcfg['fps']}|{fcfg.get('lut')}|{fcfg.get('brightness')}|{encoder}"
    out = cache / f"{hashlib.md5(key.encode()).hexdigest()[:16]}.mp4"
    if out.exists():
        return out
    vf = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
        f"fps={rcfg['fps']}",
        f"eq=brightness={fcfg.get('brightness') or 0}",
    ]
    if fcfg.get("lut"):
        lut = Path(fcfg["lut"]).resolve().as_posix().replace(":", r"\:")  # an toàn với C:/ trên Windows
        vf.append(f"lut3d=file='{lut}'")
    vf.append("format=yuv420p")
    tmp = out.with_suffix(".tmp.mp4")
    ff.run(["-i", src, "-an", "-vf", ",".join(vf), *ff.video_codec_args(encoder), tmp])
    tmp.rename(out)
    return out


def plan_sequence(durations: dict[Path, float], total: float, rng: random.Random) -> list[Path]:
    """Xáo trộn clip, lặp lại với thứ tự mới cho tới khi đủ độ dài; không để 1 clip đứng liền nhau."""
    clips = list(durations)
    seq: list[Path] = []
    acc = 0.0
    while acc < total:
        order = clips[:]
        rng.shuffle(order)
        if seq and len(order) > 1 and order[0] == seq[-1]:
            order.append(order.pop(0))
        for c in order:
            seq.append(c)
            acc += durations[c]
            if acc >= total:
                break
    return seq


def footage_track(total: float, out: Path, rcfg: dict, encoder: str) -> Path:
    fcfg = rcfg["footage"]
    folder = Path(fcfg["dir"]) / (fcfg.get("tone") or "")
    sources = _files(folder, VIDEO_EXT)
    if not sources:
        raise FileNotFoundError(f"Không có footage trong {folder}")
    cache = Path(fcfg["dir"]) / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    norm = [_normalize_clip(s, cache, rcfg, encoder) for s in sources]
    durations = {p: ff.duration(p) for p in norm}
    seq = plan_sequence(durations, total, random.Random(fcfg.get("seed")))
    lst = ff.concat_list(seq, out.with_suffix(".txt"))
    ff.run(["-f", "concat", "-safe", "0", "-i", lst, "-t", f"{total:.2f}", "-c", "copy", out])
    return out


# ---------------------------------------------------------------- Chế độ 2: ảnh tĩnh động

def kenburns_filter(W: int, H: int, fps: int, zoom: float, period: float, zoom_out_first: bool) -> str:
    # Zoom in/out rất chậm dạng cos (mượt, không giật đầu/cuối chu kỳ). Upscale 2x trước để giảm rung.
    phase = "1+cos" if zoom_out_first else "1-cos"
    z = f"1+{zoom}*({phase}(2*PI*on/{period * fps}))/2"
    return (
        f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
    )


def still_track(images: list[Path], total: float, out: Path, rcfg: dict, encoder: str) -> Path:
    W, H = rcfg["resolution"]
    fps = rcfg["fps"]
    scfg = rcfg["still"]
    seg_len = total / len(images)
    overlay = scfg.get("overlay")
    segments: list[Path] = []
    for i, img in enumerate(images):
        seg = out.parent / f"seg_{i:02d}.mp4"
        fade = min(1.0, seg_len / 4)
        chain = (
            kenburns_filter(W, H, fps, scfg["zoom"], scfg["zoom_period"], i % 2 == 1)
            + f",fade=t=in:st=0:d={fade},fade=t=out:st={seg_len - fade:.3f}:d={fade}"
        )
        args = ["-loop", "1", "-framerate", fps, "-t", f"{seg_len:.3f}", "-i", img]
        if overlay:
            args += ["-stream_loop", "-1", "-i", overlay]
            graph = (
                f"[0:v]{chain},format=gbrp[bg];"
                f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},format=gbrp[ov];"
                f"[bg][ov]blend=all_mode=screen:all_opacity={scfg['overlay_opacity']}:shortest=1,format=yuv420p[v]"
            )
            args += ["-filter_complex", graph, "-map", "[v]"]
        else:
            args += ["-vf", chain + ",format=yuv420p"]
        ff.run([*args, "-t", f"{seg_len:.3f}", *ff.video_codec_args(encoder), seg])
        segments.append(seg)
        print(f"  [render] cảnh {i + 1}/{len(images)}")
    lst = ff.concat_list(segments, out.with_suffix(".txt"))
    ff.run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    return out


# ---------------------------------------------------------------- Âm thanh

def music_playlist(music_dir: Path, total: float, rng: random.Random) -> list[Path]:
    tracks = _files(music_dir, AUDIO_EXT)
    if not tracks:
        return []
    durations = {t: ff.duration(t) for t in tracks}
    return plan_sequence(durations, total, rng)


def build_mix_graph(n_music: int, total: float, lead_in: float, acfg: dict) -> str:
    fmt = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"
    voice = f"[0:a]{fmt},adelay={int(lead_in * 1000)}:all=1,apad=whole_dur={total:.3f}"
    tail = f"afade=t=in:d={acfg['fade_in']},afade=t=out:st={max(0, total - acfg['fade_out']):.3f}:d={acfg['fade_out']}"
    if acfg.get("loudnorm", True):
        tail += ",loudnorm=I=-16:TP=-1.5:LRA=11"
    if n_music == 0:
        return f"{voice},atrim=0:{total:.3f},{tail}[out]"

    parts = [f"[{i + 1}:a]{fmt}[m{i}]" for i in range(n_music)]
    parts.append("".join(f"[m{i}]" for i in range(n_music)) + f"concat=n={n_music}:v=0:a=1,atrim=0:{total:.3f}[bed]")
    if acfg.get("ducking", "sidechain") == "sidechain":
        parts.append(f"{voice},asplit=2[vo][sc]")
        parts.append(f"[bed]volume={acfg['music_db_idle']}dB[mus]")
        parts.append("[mus][sc]sidechaincompress=threshold=0.02:ratio=12:attack=20:release=700:knee=4[duck]")
        parts.append(f"[vo][duck]amix=inputs=2:duration=first:normalize=0,{tail}[out]")
    else:
        parts.append(f"{voice}[vo]")
        parts.append(f"[bed]volume={acfg['music_db']}dB[mus]")
        parts.append(f"[vo][mus]amix=inputs=2:duration=first:normalize=0,{tail}[out]")
    return ";".join(parts)


def mix_audio(voice: Path, total: float, out: Path, rcfg: dict, seed=None) -> Path:
    acfg = rcfg["audio"]
    playlist = music_playlist(Path(acfg["music_dir"]), total, random.Random(seed))
    args = ["-i", voice]
    for t in playlist:
        args += ["-i", t]
    graph = build_mix_graph(len(playlist), total, rcfg["lead_in"], acfg)
    ff.run([*args, "-filter_complex", graph, "-map", "[out]", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", out])
    return out


# ---------------------------------------------------------------- Ghép cuối

def render(voice: Path, images: list[Path], work: Path, rcfg: dict) -> Path:
    encoder = ff.pick_encoder(rcfg.get("encoder", "auto"))
    print(f"  [render] encoder: {encoder}")
    total = rcfg["lead_in"] + ff.duration(voice) + rcfg["tail"]
    rdir = work / "render"
    rdir.mkdir(exist_ok=True)

    audio = mix_audio(voice, total, rdir / "mix.m4a", rcfg, seed=rcfg["footage"].get("seed"))
    if rcfg["mode"] == "footage":
        video = footage_track(total, rdir / "bg.mp4", rcfg, encoder)
    elif rcfg["mode"] in ("still", "thumbnail"):
        video = still_track(images, total, rdir / "bg.mp4", rcfg, encoder)
    else:
        raise ValueError(f"render.mode không hỗ trợ: {rcfg['mode']}")

    out = work / "video.mp4"
    ff.run(["-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy",
            "-t", f"{total:.3f}", "-movflags", "+faststart", out])
    return out
