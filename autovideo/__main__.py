"""CLI:
  python -m autovideo auto -c config.yaml        # TỰ ĐỘNG: mọi chủ đề -> ready/ (dùng cho lịch chạy hằng ngày)
  python -m autovideo run <url|audio|text.txt> [...] [-c config.yaml]

Ví dụ:
  python -m autovideo auto -c config.yaml --topic tam_su_dem_khuya --per-topic 2
  python -m autovideo auto -c config.yaml --dry-run   # chỉ xem sẽ lấy truyện nào
  python -m autovideo run https://www.bilibili.com/video/BV1xxxx -c config.yaml
  python -m autovideo run truyen.txt --genre hien_dai --mode footage
  python -m autovideo run --batch urls.txt
  python -m autovideo run --keyword "古风 有声小说" --limit 3
  python -m autovideo run <url> --stages translate,tts      # chạy lại vài bước
"""
from __future__ import annotations

import argparse
import sys
import traceback

from .config import load_config
from .pipeline import STAGES, Job


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="autovideo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="chạy pipeline")
    run.add_argument("sources", nargs="*", help="URL, file audio, hoặc file .txt tiếng Trung")
    run.add_argument("-c", "--config", help="file YAML (mặc định: config.example.yaml)")
    run.add_argument("--batch", help="file chứa danh sách nguồn, mỗi dòng 1 cái")
    run.add_argument("--keyword", action="append", default=[], help="tìm nguồn theo từ khóa (lặp được)")
    run.add_argument("--limit", type=int, help="số kết quả mỗi từ khóa")
    run.add_argument("--stages", help=f"chỉ chạy các bước: {','.join(STAGES)}")
    run.add_argument("--genre", help="co_trang | hien_dai")
    run.add_argument("--mode", choices=["footage", "still"])
    run.add_argument("--name", help="tên thư mục job (chỉ khi có 1 nguồn)")

    auto = sub.add_parser("auto", help="tự động theo chủ đề trong config (topics:)")
    auto.add_argument("-c", "--config", help="file YAML")
    auto.add_argument("--topic", action="append", help="chỉ chạy chủ đề này (lặp được)")
    auto.add_argument("--per-topic", type=int, help="số video mới mỗi chủ đề")
    auto.add_argument("--dry-run", action="store_true", help="chỉ tìm và liệt kê, không xử lý")
    args = ap.parse_args(argv)

    if args.cmd == "auto":
        from .auto import run_auto

        produced = run_auto(load_config(args.config), args.topic, args.per_topic, args.dry_run)
        print(f"Hoàn tất: {len(produced)} video sẵn sàng đăng.")
        return 0

    overrides: dict = {}
    if args.genre:
        overrides["genre"] = args.genre
    if args.mode:
        overrides.setdefault("render", {})["mode"] = args.mode
    cfg = load_config(args.config, overrides)

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

    stages = args.stages.split(",") if args.stages else None
    if stages and (bad := set(stages) - set(STAGES)):
        ap.error(f"bước không hợp lệ: {bad}")

    failed = 0
    for src in sources:
        try:
            Job(src, cfg, name=args.name if len(sources) == 1 else None).run(stages)
        except Exception:  # batch: lỗi 1 video không chặn các video sau
            failed += 1
            traceback.print_exc()
            print(f"[lỗi] {src}", file=sys.stderr)
    print(f"Hoàn tất {len(sources) - failed}/{len(sources)} video.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
