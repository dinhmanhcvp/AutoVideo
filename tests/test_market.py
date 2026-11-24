import pytest

from autovideo import market


def vr(vid, title, views, published, length, channel):
    return {"videoRenderer": {"videoId": vid, "title": {"runs": [{"text": title}]},
                              "viewCountText": {"simpleText": f"{views:,} lượt xem".replace(",", ".")},
                              "publishedTimeText": {"simpleText": published},
                              "lengthText": {"simpleText": length},
                              "ownerText": {"runs": [{"text": channel}]}}}


DATA = {"contents": {"x": [
    vr("a", "[Truyện Audio] Tôi Đòi Ly Hôn, Tạ Tổng Hoảng Rồi", 70000, "7 ngày trước", "55:10", "Mèo Audio"),
    vr("b", "[Truyện Audio] Vợ Ngoan Bỗng Né Tránh", 3000, "3 tuần trước", "1:02:00", "Kem Audio"),
    vr("c", "Review phim: Tổng tài bá đạo", 900000, "2 ngày trước", "45:00", "Hùng Tổng Review"),
    vr("d", "[Truyện Audio] Ngắn quá", 50000, "1 ngày trước", "8:00", "Mèo Audio"),
    {"other": [vr("e", "Truyện audio cũ", 999999, "2 tháng trước", "50:00", "X Audio")]},
]}}


def test_parse_helpers():
    assert market.parse_age_days("3 tuần trước") == 21
    assert market.parse_age_days("Đã phát trực tiếp 5 giờ trước") == pytest.approx(5 / 24)
    assert market.parse_views("1.445 lượt xem") == 1445
    assert market.parse_length_min("1:02:00") == 62


def test_metrics_keep_only_recent_long_audio_and_separate_recaps():
    rows = market.video_rows(DATA)
    assert len(rows) == 5
    m = market.niche_metrics(rows)
    # giữ a, b (truyện audio dài, trong tháng); loại d (ngắn), e (cũ); c là review phim
    assert m["n"] == 2 and m["recap_n"] == 1
    assert m["median_vpd"] == 5072  # trung vị của 10.000 và 143 view/ngày
    assert m["hit_rate"] == 0.5 and m["hit_channels"] == 1
    assert 0 < market.opportunity(m) <= 100


def test_report_keeps_commas_in_labels():
    rows = market.video_rows(DATA)
    m = market.niche_metrics(rows)
    m["score"], m["label"] = market.opportunity(m), "Ngôn tình, tổng tài"
    md = market.report_md({"x": m}, "2026-11-24")
    assert "Ngôn tình, tổng tài" in md and "10.000" in md
