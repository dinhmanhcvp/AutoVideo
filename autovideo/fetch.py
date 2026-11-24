"""Module 1a: tải audio nguồn bằng yt-dlp (Bilibili, Douyin, YouTube, Ximalaya...)."""
from __future__ import annotations

from pathlib import Path


def search(keyword: str, site: str = "bilisearch", limit: int = 3) -> list[dict]:
    """Tìm theo từ khóa. site: bilisearch (Bilibili) | ytsearch (YouTube).
    Trả về [{url, title, duration, site}] — duration (giây) có thể None nếu nguồn không cung cấp."""
    import yt_dlp

    opts = {"quiet": True, "extract_flat": True, "skip_download": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{site}{limit}:{keyword}", download=False) or {}
    results = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        url = entry.get("webpage_url") or entry.get("url")
        if url:
            results.append({
                "url": url,
                "title": entry.get("title") or "",
                "duration": entry.get("duration"),
                "site": site,
            })
    return results


def download_audio(url: str, out_dir: Path, cookies_file: str | None = None) -> tuple[Path, dict]:
    """Tải audio tốt nhất về out_dir/source.<ext> (m4a qua FFmpeg). Trả về (path, info)."""
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    path = out_dir / "source.m4a"
    if not path.exists():
        candidates = sorted(out_dir.glob("source.*"))
        if not candidates:
            raise RuntimeError(f"yt-dlp không tạo ra file audio cho {url}")
        path = candidates[0]
    meta = {k: info.get(k) for k in ("id", "title", "uploader", "duration", "webpage_url")}
    return path, meta
