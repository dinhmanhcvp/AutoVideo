"""`python -m autovideo market`: khảo sát thị trường truyện audio tiếng Việt trên YouTube theo ngách.

Mỗi ngách: tìm bằng vài từ khóa người Việt hay gõ, chỉ lấy VIDEO DÀI (>20 phút) đăng TRONG THÁNG
(cả danh sách xem nhiều nhất lẫn liên quan nhất), rồi tính:
  - lượt xem/ngày: trung vị (độ đều) và P75 (trần khá)
  - tỷ lệ "trúng": % video ≥ 1.000 view/ngày
  - số kênh khác nhau có video trúng (nhiều kênh cùng ăn = cầu rộng, người mới dễ vào)
  - mức độ cạnh tranh: số video mới tìm thấy
Điểm cơ hội = kết hợp các chỉ số trên. Chạy lại hằng tháng để theo dõi xu hướng.
"""
from __future__ import annotations

import json
import re
import statistics
import time
from datetime import date
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
# Bộ lọc tìm kiếm YouTube (protobuf base64): video dài >20 phút, đăng trong tháng
SP_MOST_VIEWED_MONTH_LONG = "CAMSBAgEGAI="
SP_RELEVANT_MONTH_LONG = "EgQIBBgC"

NICHES: dict[str, dict] = {
    "ngon_tinh_hien_dai": {"label": "Ngôn tình hiện đại / tổng tài",
                           "queries": ["truyện ngôn tình audio", "truyện tổng tài", "truyện ngôn tình hiện đại hay"]},
    "nu_cuong_va_mat": {"label": "Nữ cường, vả mặt, trọng sinh báo thù",
                        "queries": ["truyện trọng sinh báo thù", "truyện vả mặt", "truyện nữ cường"]},
    "drama_gia_dinh": {"label": "Drama gia đình, mẹ chồng nàng dâu, ngoại tình",
                       "queries": ["truyện mẹ chồng nàng dâu", "truyện ngoại tình", "truyện gia đình audio"]},
    "hai_huoc": {"label": "Hài hước, \"mỏ hỗn\", sảng văn đời thường",
                 "queries": ["truyện hài audio", "truyện mỏ hỗn", "truyện hài hước gia đình"]},
    "pha_an": {"label": "Phá án, trinh thám, hình sự",
               "queries": ["truyện phá án", "truyện trinh thám audio", "truyện hình sự có thật"]},
    "kinh_di": {"label": "Truyện ma, kinh dị, tâm linh",
                "queries": ["truyện ma audio", "truyện ma có thật", "truyện kinh dị audio"]},
    "tam_su": {"label": "Tâm sự đêm khuya, chuyện đời thật",
               "queries": ["tâm sự đêm khuya", "truyện tâm sự cuộc sống", "radio tâm sự"]},
    "co_trang": {"label": "Cổ trang, cung đấu, ngôn tình cổ đại",
                 "queries": ["truyện cổ trang audio", "truyện cung đấu", "truyện ngôn tình cổ đại"]},
    "tu_tien": {"label": "Tu tiên, tiên hiệp, huyền huyễn",
                "queries": ["truyện tu tiên", "truyện tiên hiệp audio", "truyện huyền huyễn"]},
    "thanh_xuan": {"label": "Thanh xuân, thầm thích, học đường",
                   "queries": ["truyện thanh xuân", "truyện thầm thích", "truyện học đường audio"]},
    "xuyen_khong_he_thong": {"label": "Xuyên không, hệ thống, xuyên sách",
                             "queries": ["truyện xuyên không", "truyện hệ thống", "truyện xuyên sách"]},
    "zhihu_truyen_ngan": {"label": "Truyện ngắn Zhihu (twist, nhiều thể loại)",
                          "queries": ["truyện zhihu", "truyện ngắn zhihu", "truyện ngắn trung quốc audio"]},
}

_UNITS = {"giây": 1 / 86400, "phút": 1 / 1440, "giờ": 1 / 24, "ngày": 1, "tuần": 7, "tháng": 30, "năm": 365}


def parse_age_days(text: str) -> float | None:
    m = re.search(r"(\d+)\s*(giây|phút|giờ|ngày|tuần|tháng|năm)", text or "")
    return int(m.group(1)) * _UNITS[m.group(2)] if m else None


def parse_views(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def parse_length_min(text: str) -> float:
    parts = [int(p) for p in (text or "0").split(":") if p.isdigit()]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs / 60


def _walk_videos(node):
    if isinstance(node, dict):
        if "videoRenderer" in node:
            yield node["videoRenderer"]
        for v in node.values():
            yield from _walk_videos(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_videos(v)


def video_rows(data) -> list[dict]:
    rows = []
    for v in _walk_videos(data):
        try:
            title = "".join(r["text"] for r in v["title"]["runs"])
        except (KeyError, TypeError):
            continue
        age = parse_age_days(v.get("publishedTimeText", {}).get("simpleText", ""))
        views = parse_views(v.get("viewCountText", {}).get("simpleText", ""))
        if age is None:
            continue
        rows.append({
            "id": v.get("videoId"), "title": title, "views": views, "age_days": round(max(age, 0.5), 2),
            "views_per_day": round(views / max(age, 0.5)),
            "length_min": round(parse_length_min(v.get("lengthText", {}).get("simpleText", "")), 1),
            "channel": (v.get("ownerText", {}).get("runs") or [{}])[0].get("text", ""),
        })
    return rows


class YouTubeSearch:
    """Đọc trang kết quả tìm kiếm công khai của YouTube (trang đầu, ~20 video/lượt)."""

    def __init__(self, delay: float = 1.5):
        import requests

        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9"})
        self.delay = delay

    def search(self, query: str, sp: str) -> list[dict]:
        r = self.s.get("https://www.youtube.com/results",
                       params={"search_query": query, "sp": sp, "hl": "vi", "gl": "VN"}, timeout=30)
        r.raise_for_status()
        time.sleep(self.delay)
        m = re.search(r"var ytInitialData = (\{.*?\});</script>", r.text, re.S)
        return video_rows(json.loads(m.group(1))) if m else []


AUDIO_STORY = re.compile(r"truyện|audio|radio|tâm sự|kể chuyện|đọc truyện|full bộ|trọn bộ", re.I)
RECAP = re.compile(r"review|phim|tóm tắt phim|recap", re.I)


def classify(row: dict) -> str:
    text = f"{row['title']} {row['channel']}"
    if AUDIO_STORY.search(text) and not RECAP.search(row["channel"]):
        return "audio"
    if RECAP.search(text):
        return "recap"
    return "other"


def niche_metrics(rows: list[dict], hit_vpd: int = 1000) -> dict:
    rows = [r for r in rows if r["length_min"] >= 20 and r["age_days"] <= 31]
    recap = [r for r in rows if classify(r) == "recap"]
    rows = [r for r in rows if classify(r) == "audio"]
    if not rows:
        return {"n": 0, "recap_n": len(recap)}
    vpd = sorted(r["views_per_day"] for r in rows)
    hits = [r for r in rows if r["views_per_day"] >= hit_vpd]
    q = statistics.quantiles(vpd, n=4) if len(vpd) >= 4 else [vpd[0], vpd[len(vpd) // 2], vpd[-1]]
    return {
        "n": len(rows),
        "median_vpd": round(statistics.median(vpd)),
        "p75_vpd": round(q[2]),
        "top_vpd": vpd[-1],
        "hit_rate": round(len(hits) / len(rows), 2),
        "hit_channels": len({r["channel"] for r in hits}),
        "channels": len({r["channel"] for r in rows}),
        "median_len_min": round(statistics.median(r["length_min"] for r in rows)),
        "top_videos": sorted(rows, key=lambda r: -r["views_per_day"])[:5],
        "recap_n": len(recap),
        "recap_median_vpd": round(statistics.median(r["views_per_day"] for r in recap)) if recap else 0,
    }


def opportunity(m: dict) -> float:
    """Điểm cơ hội 0–100: độ đều (trung vị) + trần (P75) + tỷ lệ trúng + độ rộng (số kênh trúng)."""
    import math

    if not m.get("n"):
        return 0.0
    s_med = min(1.0, math.log10(1 + m["median_vpd"]) / 4)      # 10k view/ngày ~ tối đa
    s_p75 = min(1.0, math.log10(1 + m["p75_vpd"]) / 4.5)
    s_hit = m["hit_rate"]
    s_breadth = min(1.0, m["hit_channels"] / 10)
    return round(100 * (0.35 * s_med + 0.2 * s_p75 + 0.25 * s_hit + 0.2 * s_breadth), 1)


def run_market(out_dir: str | Path = "output/market", niches: dict | None = None) -> dict:
    niches = niches or NICHES
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    yts = YouTubeSearch()
    result, raw = {}, {}
    for key, n in niches.items():
        rows: dict[str, dict] = {}
        for q in n["queries"]:
            for sp in (SP_MOST_VIEWED_MONTH_LONG, SP_RELEVANT_MONTH_LONG):
                try:
                    for r in yts.search(q, sp):
                        rows[r["id"]] = r
                except Exception as e:
                    print(f"  [market] lỗi '{q}': {e}")
        raw[key] = list(rows.values())
        m = niche_metrics(raw[key])
        m["score"] = opportunity(m)
        m["label"] = n["label"]
        result[key] = m
        print(f"  {n['label']:<48} {m.get('n', 0):>3} video · trung vị {m.get('median_vpd', 0):>6}/ngày · "
              f"trúng {m.get('hit_rate', 0):.0%} · {m.get('hit_channels', 0)} kênh trúng · điểm {m['score']}")
    stamp = date.today().isoformat()
    (out / f"market_{stamp}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"market_{stamp}_raw.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    (out / f"market_{stamp}.md").write_text(report_md(result, stamp), encoding="utf-8")
    return result


def _n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def report_md(result: dict, stamp: str) -> str:
    ranked = sorted(result.items(), key=lambda kv: -kv[1].get("score", 0))
    lines = [f"# Khảo sát ngách truyện audio — {stamp}", "",
             "Video dài >20 phút đăng trong 31 ngày gần nhất, tìm trên YouTube Việt Nam.", "",
             "| # | Ngách | Video mẫu | Trung vị view/ngày | P75 | % trúng (≥1k/ngày) | Kênh trúng | Độ dài TV | Điểm |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, (k, m) in enumerate(ranked, 1):
        if not m.get("n"):
            lines.append(f"| {i} | {m['label']} | 0 | – | – | – | – | – | 0 |")
            continue
        lines.append(f"| {i} | {m['label']} | {m['n']} | {_n(m['median_vpd'])} | {_n(m['p75_vpd'])} | "
                     f"{m['hit_rate']:.0%} | {m['hit_channels']}/{m['channels']} | {m['median_len_min']}' | "
                     f"**{m['score']}** |")
    lines.append("")
    for k, m in ranked[:4]:
        if not m.get("n"):
            continue
        lines.append(f"## {m['label']} — video nổi nhất tháng")
        for r in m["top_videos"]:
            lines.append(f"- {_n(r['views_per_day'])} view/ngày · {_n(r['views'])} view · {r['length_min']:.0f}' · "
                         f"{r['channel']} — {r['title']}")
        lines.append("")
    return "\n".join(lines)
