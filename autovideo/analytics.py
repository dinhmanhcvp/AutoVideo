"""Vòng phản hồi: đo hiệu quả từng video trên YouTube -> báo cáo -> dồn sản lượng cho chủ đề ăn khách.

- fetch_stats: lượt xem/thích/bình luận (YouTube Data API) + thời lượng xem trung bình, % giữ chân
  (YouTube Analytics API, nếu đã cấp quyền) cho mọi video đã đăng qua bot.
- plan_quotas: chia `auto.daily_total` video/ngày cho các chủ đề theo lượt xem/ngày trung bình;
  chủ đề chưa có dữ liệu được ưu tiên thử (khám phá) để không bỏ lỡ ngách mới.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date, datetime, timezone
from pathlib import Path


def analytics_file(cfg: dict) -> Path:
    return Path(cfg["workdir"]) / "analytics.json"


def load_stats(cfg: dict) -> dict:
    path = analytics_file(cfg)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _published_videos(cfg: dict) -> dict[str, dict]:
    path = Path(cfg["review"]["state_file"])
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["youtube_id"]: r for r in data.values()
            if r.get("youtube_id") and r.get("status") in ("published", "scheduled")}


def fetch_stats(cfg: dict, yt=None, yta=None) -> dict:
    """Cập nhật analytics.json. yt/yta: client YouTube Data / Analytics (để test có thể truyền giả)."""
    from . import youtube

    videos = _published_videos(cfg)
    if not videos:
        return load_stats(cfg)
    if yt is None:
        yt, yta = youtube.service(cfg["youtube"]), youtube.analytics_service(cfg["youtube"])
    stats = load_stats(cfg)
    ids = list(videos)
    now = datetime.now(timezone.utc)
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="statistics,snippet,status", id=",".join(ids[i:i + 50])).execute()
        for item in resp.get("items", []):
            st, sn = item.get("statistics", {}), item.get("snippet", {})
            published = sn.get("publishedAt")
            age_days = None
            if published:
                age_days = (now - datetime.fromisoformat(published.replace("Z", "+00:00"))).total_seconds() / 86400
            rec = videos[item["id"]]
            stats[item["id"]] = {
                **stats.get(item["id"], {}),
                "topic": rec.get("topic", ""), "title": sn.get("title", rec.get("title", "")),
                "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)), "published": published,
                "age_days": round(age_days, 2) if age_days is not None else None,
                "privacy": item.get("status", {}).get("privacyStatus"),
                "checked": now.isoformat(timespec="minutes"),
            }
    if yta is not None:
        try:
            start = min((v["published"] or now.isoformat())[:10] for v in stats.values() if v.get("published"))
            resp = yta.reports().query(
                ids="channel==MINE", startDate=start, endDate=date.today().isoformat(),
                metrics="views,averageViewDuration,averageViewPercentage", dimensions="video",
                filters="video==" + ",".join(ids[:200]), maxResults=200,
            ).execute()
            for row in resp.get("rows", []):
                vid, _, avd, avp = row
                if vid in stats:
                    stats[vid].update(avg_view_seconds=round(avd), avg_view_percent=round(avp, 1))
        except Exception as e:  # chưa bật YouTube Analytics API / chưa cấp quyền: bỏ qua phần giữ chân
            print(f"  [analytics] bỏ qua số liệu giữ chân: {e}")
    analytics_file(cfg).write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    return stats


def views_per_day(rec: dict) -> float | None:
    """Lượt xem/ngày, chỉ tính video đã đăng ≥ 2 ngày (tránh nhiễu giờ đầu)."""
    age = rec.get("age_days")
    if age is None or age < 2 or rec.get("privacy") not in (None, "public"):
        return None
    return rec["views"] / age


def topic_scores(stats: dict, last_n: int = 10) -> dict[str, float]:
    by_topic: dict[str, list[tuple[str, float]]] = {}
    for rec in stats.values():
        vpd = views_per_day(rec)
        if vpd is not None:
            by_topic.setdefault(rec.get("topic", ""), []).append((rec.get("published") or "", vpd))
    return {t: statistics.mean(v for _, v in sorted(items)[-last_n:]) for t, items in by_topic.items()}


def plan_quotas(cfg: dict, topics: list[dict], per_topic: int | None = None) -> dict[str, int]:
    acfg = cfg["auto"]
    if per_topic:
        return {t["name"]: per_topic for t in topics}
    total = acfg.get("daily_total")
    if not acfg.get("adaptive") or not total:
        return {t["name"]: acfg.get("per_topic", 1) for t in topics}
    scores = topic_scores(load_stats(cfg))
    known = [scores[t["name"]] for t in topics if t["name"] in scores]
    optimistic = max(known) if known else 1.0  # chủ đề mới: coi như tốt nhất để được thử
    weights = {t["name"]: max(scores.get(t["name"], optimistic), 0.1) ** acfg.get("adaptive_power", 1.0)
               for t in topics}
    s = sum(weights.values()) or 1
    raw = {k: total * w / s for k, w in weights.items()}
    quotas = {k: math.floor(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - quotas[k], reverse=True)[: total - sum(quotas.values())]:
        quotas[k] += 1
    for t in topics:  # khám phá: chủ đề chưa có dữ liệu luôn được ít nhất 1 nếu còn chỗ
        if t["name"] not in scores and quotas[t["name"]] == 0:
            donor = max(quotas, key=quotas.get)
            if quotas[donor] > 1:
                quotas[donor] -= 1
                quotas[t["name"]] = 1
    return quotas


def report_text(cfg: dict, stats: dict | None = None) -> str:
    stats = load_stats(cfg) if stats is None else stats
    if not stats:
        return "Chưa có số liệu. Cần bật youtube.enabled và đăng video qua bot trước."
    lines = ["📊 BÁO CÁO KÊNH"]
    total_views = sum(r["views"] for r in stats.values())
    lines.append(f"{len(stats)} video · {total_views:,} lượt xem".replace(",", "."))
    scores = topic_scores(stats)
    if scores:
        lines.append("\nChủ đề (lượt xem/ngày trung bình):")
        for t, v in sorted(scores.items(), key=lambda kv: -kv[1]):
            ret = [r.get("avg_view_percent") for r in stats.values() if r.get("topic") == t and r.get("avg_view_percent")]
            extra = f" · giữ chân {statistics.mean(ret):.0f}%" if ret else ""
            lines.append(f"• {t}: {v:.0f}{extra}")
    ranked = sorted((r for r in stats.values() if views_per_day(r) is not None), key=views_per_day, reverse=True)
    if ranked:
        lines.append("\n🔥 Top video:")
        for r in ranked[:5]:
            lines.append(f"• {r['views']:,} view · {r['title'][:60]}".replace(",", "."))
        lines.append("\n🧊 Yếu nhất:")
        for r in ranked[-3:][::-1]:
            lines.append(f"• {r['views']:,} view · {r['title'][:60]}".replace(",", "."))
    low_ret = [r for r in stats.values() if r.get("avg_view_percent") is not None and r["avg_view_percent"] < 25]
    if low_ret:
        lines.append(f"\n⚠ {len(low_ret)} video giữ chân < 25%: người xem bỏ sớm — xem lại hook/đoạn đầu của các truyện này.")
    if scores and len(scores) > 1:
        best = max(scores, key=scores.get)
        lines.append(f"\n💡 Chủ đề hiệu quả nhất: {best}. Bật auto.adaptive để máy tự dồn thêm video cho chủ đề này.")
    return "\n".join(lines)
