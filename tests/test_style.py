import json

from PIL import Image, ImageDraw

from autovideo import auto, thumbnail
from autovideo.config import load_config
from autovideo.pipeline import Job
from autovideo.translate import final_title, normalize_metadata


def test_final_title_template_and_length():
    cfg = load_config()
    meta = {"story_title": "Cả Nhà Tôi Đều Là Cao Thủ Mỏ Hỗn Có Tri Thức", "youtube_title": "x"}
    assert final_title(meta, cfg) == \
        "[Truyện Audio] Cả Nhà Tôi Đều Là Cao Thủ Mỏ Hỗn Có Tri Thức (Full) | Đêm Nghe Truyện"
    long = {"story_title": "Rất " * 30}
    assert len(final_title(long, cfg)) <= 100 and "|" not in final_title(long, cfg)
    cfg["channel"]["title_template"] = None
    assert final_title(meta, cfg) == "x"


def test_highlights_only_kept_if_in_story_title():
    meta = normalize_metadata({"story_title": "Thiếu Gia Ăn Chơi Gặp Đúng Khắc Tinh",
                               "thumb_highlight": ["Khắc Tinh", "Không Có"], "image_prompt": "p"}, load_config())
    assert meta["thumb_highlight"] == ["Khắc Tinh"]


def test_highlight_phrase_never_split_across_lines():
    words = "CẢ NHÀ TÔI ĐỀU LÀ CAO THỦ MỎ HỖN CÓ TRI THỨC".split()
    colors = thumbnail.mark_highlights(words, ["Mỏ Hỗn", "Tri Thức"], ["red", "green"], "base")
    assert colors[7:9] == ["red", "red"] and colors[10:] == ["green", "green"]
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for width in range(250, 700, 25):
        font, lines, _ = thumbnail.layout_title(draw, words, None, width, 500,
                                                units=thumbnail._units(words, colors, "base"))
        for line in lines:
            assert not (7 in line) ^ (8 in line)  # "MỎ HỖN" luôn cùng dòng


def test_split_thumbnail_renders(tmp_path):
    bg = thumbnail.placeholder_background("x", tmp_path / "bg.png")
    cfg = dict(load_config()["thumbnail"], badge="Kênh · Số 3")
    meta = {"story_title": "Chiếc Túi Da Người Và Lời Nói Dối 18 Năm", "thumb_highlight": ["18 Năm"]}
    out = thumbnail.render_thumbnail(bg, meta, tmp_path / "t.jpg", cfg)
    assert Image.open(out).size == (1280, 720)


def test_episode_numbering_and_title_written(tmp_path):
    cfg = load_config(overrides={"workdir": str(tmp_path), "channel": {"episode_start": 397}})
    for n, name in [(397, "a"), (398, "b")]:
        job = Job(name, cfg, name=name)
        job.p("metadata.json").write_text(json.dumps(normalize_metadata(
            {"story_title": f"Truyện {name}", "image_prompt": "p"}, cfg)), encoding="utf-8")
        job.thumbnail()
        meta = json.loads(job.p("metadata.json").read_text(encoding="utf-8"))
        assert meta["episode"] == n
        assert meta["youtube_title"].startswith(f"[Truyện Audio] Truyện {name}")
        job.thumbnail()  # chạy lại không tăng số tập
        assert json.loads(job.p("metadata.json").read_text(encoding="utf-8"))["episode"] == n


def test_disabled_topics_skipped_unless_named():
    cfg = load_config()
    seen = []
    auto.run_auto(cfg, dry_run=True, search_fn=lambda kw, site, n: seen.append(kw) or [])
    assert any("豪门" in k for k in seen) and not any("古风" in k or "沙雕" in k for k in seen)
    seen.clear()
    auto.run_auto(cfg, topics=["co_trang_tu_tien"], dry_run=True, search_fn=lambda kw, site, n: seen.append(kw) or [])
    assert any("古风" in k for k in seen)
