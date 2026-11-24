"""`python -m autovideo brand`: xem trước nhận diện kênh (thumbnail 3 phương án + khung clip TikTok) cho
mọi chủ đề đang bật, gom vào 1 ảnh tổng output/brand_preview/index.jpg. Dùng để chỉnh màu/font/mascot
trước khi sản xuất hàng loạt. --real: vẽ ảnh nền thật bằng image_engine (tốn phí ảnh)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

SAMPLES = {
    "ngon_tinh": ("Tôi Đòi Ly Hôn, Hoắc Tổng Lại Khóc Lóc Không Buông", ["Ly Hôn", "Không Buông"]),
    "hai_huoc": ("Cả Nhà Tôi Đều Là Cao Thủ Mỏ Hỗn Có Tri Thức", ["Mỏ Hỗn", "Tri Thức"]),
    "pha_an": ("Chiếc Túi Da Người Và Lời Nói Dối 18 Năm", ["18 Năm"]),
    "hien_dai": ("Thiếu Gia Ăn Chơi Gặp Đúng Khắc Tinh", ["Khắc Tinh"]),
    "tam_su": ("Ba Năm Tôi Giả Vờ Không Biết Chồng Ngoại Tình", ["Giả Vờ"]),
    "co_trang": ("Sư Tôn Lạnh Lùng Và Đồ Nhi Bị Cả Tông Môn Ruồng Bỏ", ["Ruồng Bỏ"]),
    "kinh_di": ("Đêm Đó Có Người Gõ Cửa Từ Bên Trong Quan Tài", ["Bên Trong"]),
}


def run_brand(cfg: dict, real: bool = False) -> Path:
    from .auto import topic_config
    from .doctor import active_topics
    from .hook import tiktok_frame
    from .package import render_variants
    from .thumbnail import make_background, placeholder_background

    out = Path(cfg["workdir"]) / "brand_preview"
    out.mkdir(parents=True, exist_ok=True)
    rows: list[list[Path]] = []
    for i, topic in enumerate(active_topics(cfg) or cfg["topics"][:1]):
        tcfg = topic_config(cfg, topic)
        title, hl = SAMPLES.get(tcfg["genre"], SAMPLES["hien_dai"])
        d = out / topic["name"]
        d.mkdir(exist_ok=True)
        for f in d.glob("thumbnail*.jpg"):
            f.unlink()  # luôn vẽ lại theo config mới nhất
        bg = d / "thumb_bg.png"
        prompt = f"dramatic key scene of a story titled '{title}', {tcfg['channel'].get('visual_style', '')}"
        if real and not bg.exists():
            make_background(prompt, bg, tcfg["thumbnail"])
        elif not bg.exists():
            placeholder_background(prompt, bg)
        meta = {"story_title": title, "thumb_highlight": hl, "episode": 100 + i,
                "title_variants": [{"story_title": title, "thumb_highlight": hl},
                                   {"story_title": title, "thumb_highlight": hl},
                                   {"story_title": title, "thumb_highlight": hl}]}
        th = dict(tcfg["thumbnail"])
        th["badge"] = (th.get("badge") or "").replace("{channel_name}", tcfg["channel"]["name"]) \
                                            .replace("{episode}", str(meta["episode"]))
        thumbs = render_variants(bg, meta, d, th)
        tk = tcfg["tiktok"]
        badge = (tk.get("badge") or "").replace("{channel_name}", tcfg["channel"]["name"]) \
                                       .replace("{episode}", str(meta["episode"]))
        frame = tiktok_frame(bg, meta, d / "tiktok_frame.png", tcfg["thumbnail"],
                             tk.get("banner", "").replace("{channel_name}", tcfg["channel"]["name"]), badge)
        rows.append([thumbs[0], thumbs[2], frame])
        print(f"  ✔ {topic['name']}: {d}")

    # Ảnh tổng: mỗi chủ đề 1 hàng = thumbnail + thumbnail lật bên + khung TikTok
    th_w, th_h, tk_h = 640, 360, 360
    tk_w = round(tk_h * 1080 / 1920)
    sheet = Image.new("RGB", (th_w * 2 + tk_w + 40, (th_h + 20) * len(rows) + 20), "#202020")
    for r, (a, b, f) in enumerate(rows):
        y = 20 + r * (th_h + 20)
        sheet.paste(Image.open(a).resize((th_w, th_h)), (10, y))
        sheet.paste(Image.open(b).resize((th_w, th_h)), (20 + th_w, y))
        sheet.paste(Image.open(f).resize((tk_w, tk_h)), (30 + 2 * th_w, y))
    index = out / "index.jpg"
    sheet.save(index, quality=90)
    print(f"\nẢnh tổng: {index}")
    return index
