"""AutoVideo — dây chuyền làm video truyện audio từ truyện tiếng Trung.

Bắt đầu (1 lần):
  python -m autovideo setup              hỏi đáp tạo config.yaml + .env
  python -m autovideo doctor [--online]  kiểm tra máy & khóa API, chỉ cách sửa
  python -m autovideo brand [--real]     xem trước thumbnail/clip TikTok của kênh

Hằng ngày:
  python -m autovideo bot                bot Telegram: tự chạy mỗi đêm, duyệt & đăng từ điện thoại
  python -m autovideo auto [--dry-run]   chạy 1 lượt theo chủ đề -> ready/
  python -m autovideo make <url|file>    làm 1 video từ link hoặc file .txt/.mp3 bạn chọn
  python -m autovideo report             báo cáo view/giữ chân theo chủ đề

Khác:
  python -m autovideo voices --engine google|edge|elevenlabs
  python -m autovideo make <nguồn> --stages package,render     làm lại vài bước
  (Mặc định dùng config.yaml ở thư mục hiện tại nếu có; đổi bằng -c file.yaml)
"""
from __future__ import annotations

import argparse
import sys
import traceback

from .config import load_config, load_env, resolve_config_path
from .pipeline import STAGE_ALIASES, STAGES, Job


def _cfg(args, overrides: dict | None = None) -> dict:
    return load_config(resolve_config_path(getattr(args, "config", None)), overrides)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:  # cửa sổ lệnh Windows: in được tiếng Việt
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    load_env()
    ap = argparse.ArgumentParser(prog="autovideo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("-c", "--config", help="file YAML (mặc định: config.yaml nếu có)")
        return p

    add("setup", "hỏi đáp tạo config.yaml + .env")
    p = add("doctor", "kiểm tra cài đặt")
    p.add_argument("--online", action="store_true", help="gọi thử thật LLM, giọng đọc, Telegram")
    p = add("brand", "xem trước nhận diện kênh")
    p.add_argument("--real", action="store_true", help="vẽ ảnh nền thật (tốn phí ảnh)")
    p = add("voices", "liệt kê giọng đọc tiếng Việt")
    p.add_argument("--engine", default="edge", choices=["edge", "google", "elevenlabs"])
    add("report", "báo cáo hiệu quả kênh")
    add("bot", "bot Telegram thường trực")

    p = add("auto", "chạy 1 lượt tự động theo chủ đề")
    p.add_argument("--topic", action="append", help="chỉ chạy chủ đề này (lặp được)")
    p.add_argument("--per-topic", type=int, help="số video mới mỗi chủ đề")
    p.add_argument("--dry-run", action="store_true", help="chỉ tìm và liệt kê, không xử lý")

    for name in ("make", "run"):  # run: tên cũ
        p = add(name, "làm video từ nguồn bạn chọn")
        p.add_argument("sources", nargs="*", help="URL, file audio, hoặc file .txt (tiếng Trung/Việt)")
        p.add_argument("--batch", help="file chứa danh sách nguồn, mỗi dòng 1 cái")
        p.add_argument("--keyword", action="append", default=[], help="tìm nguồn theo từ khóa")
        p.add_argument("--limit", type=int, help="số kết quả mỗi từ khóa")
        p.add_argument("--stages", help=f"chỉ chạy các bước: {','.join(STAGES)}")
        p.add_argument("--topic", help="dùng giọng/văn phong/hình của chủ đề này")
        p.add_argument("--genre", help="co_trang | hien_dai | tam_su | kinh_di | hai_huoc | pha_an")
        p.add_argument("--mode", choices=["footage", "still", "thumbnail"])
        p.add_argument("--name", help="tên thư mục job (chỉ khi có 1 nguồn)")
        p.add_argument("--export", action="store_true", help="gom thành phẩm vào ready/ (+ gửi Telegram nếu bật)")
    args = ap.parse_args(argv)

    if args.cmd == "setup":
        from .setup_wizard import run_setup

        run_setup(args.config or "config.yaml")
        return 0
    if args.cmd == "doctor":
        from .doctor import run_doctor

        return run_doctor(_cfg(args), args.online)
    if args.cmd == "brand":
        from .brand import run_brand

        run_brand(_cfg(args), args.real)
        return 0
    if args.cmd == "voices":
        from .tts import list_voices

        for v in list_voices(args.engine):
            print(v)
        return 0
    if args.cmd == "report":
        from .analytics import fetch_stats, report_text

        cfg = _cfg(args)
        print(report_text(cfg, fetch_stats(cfg) if cfg.get("youtube", {}).get("enabled") else None))
        return 0
    if args.cmd == "bot":
        from .review import Bot

        Bot(_cfg(args), resolve_config_path(args.config)).loop()
        return 0
    if args.cmd == "auto":
        from .auto import run_auto

        produced = run_auto(_cfg(args), args.topic, args.per_topic, args.dry_run)
        print(f"Hoàn tất: {len(produced)} video sẵn sàng đăng.")
        return 0
    return _make(args, ap)


def _make(args, ap) -> int:
    overrides: dict = {}
    if args.genre:
        overrides["genre"] = args.genre
    if args.mode:
        overrides.setdefault("render", {})["mode"] = args.mode
    cfg = _cfg(args)
    topic_name = args.topic
    if topic_name:
        from .auto import topic_config

        topic = next((t for t in cfg["topics"] if t["name"] == topic_name), None)
        if topic is None:
            ap.error(f"không có chủ đề {topic_name}. Có: {', '.join(t['name'] for t in cfg['topics'])}")
        cfg = topic_config(cfg, topic)
    if overrides:
        from .config import _deep_merge

        cfg = _deep_merge(cfg, overrides)

    sources = list(args.sources)
    if args.batch:
        with open(args.batch, encoding="utf-8") as f:
            sources += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    for kw in args.keyword:
        from .fetch import search

        found = search(kw, cfg["source"]["search_site"], args.limit or cfg["source"]["max_per_keyword"])
        print(f"[tìm] '{kw}': {len(found)} kết quả")
        sources += [r["url"] for r in found]
    if not sources:
        ap.error("cần ít nhất 1 nguồn (URL / file / --batch / --keyword)")

    stages = [STAGE_ALIASES.get(s, s) for s in args.stages.split(",")] if args.stages else None
    if stages and (bad := set(stages) - set(STAGES)):
        ap.error(f"bước không hợp lệ: {bad}. Các bước: {', '.join(STAGES)}")

    failed = 0
    for src in sources:
        try:
            job = Job(src, cfg, name=args.name if len(sources) == 1 else None)
            job.run(stages)
            if args.export and job.p("video.mp4").exists():
                from pathlib import Path

                from .auto import export

                dest = export(job, Path(cfg["auto"]["ready_dir"]))
                print(f"✔ Thành phẩm: {dest}")
                if cfg.get("review", {}).get("enabled"):
                    from .review import notify

                    notify(dest, cfg, topic_name or "")
        except Exception:  # batch: lỗi 1 video không chặn các video sau
            failed += 1
            traceback.print_exc()
            print(f"[lỗi] {src}", file=sys.stderr)
    print(f"Hoàn tất {len(sources) - failed}/{len(sources)} video.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
