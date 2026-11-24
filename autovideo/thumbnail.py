"""Module 4: ảnh nền (ComfyUI hoặc ảnh giữ chỗ) + đóng khung thumbnail đồng bộ nhận diện kênh."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont

FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize + crop giữa để lấp đầy size (object-fit: cover)."""
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((left, top, left + tw, top + th))


def placeholder_background(prompt: str, out: Path, size=(1920, 1080)) -> Path:
    """Ảnh gradient tối giữ chỗ khi chưa bật ComfyUI — màu suy ra từ prompt để mỗi cảnh khác nhau."""
    h = hashlib.sha256(prompt.encode()).digest()
    c1 = (h[0] // 4, h[1] // 4, h[2] // 3)
    c2 = (80 + h[3] // 2, 60 + h[4] // 3, 40 + h[5] // 3)
    w, ht = size
    grad = Image.linear_gradient("L").resize((w, ht)).rotate(h[6] % 360, expand=False)
    img = Image.composite(Image.new("RGB", size, c2), Image.new("RGB", size, c1), grad)
    img.filter(ImageFilter.GaussianBlur(30)).save(out)
    return out


def cloud_image(prompt: str, out: Path, model: str) -> Path:
    """Vẽ ảnh 16:9 bằng Google (Imagen hoặc Gemini image) — không tốn GPU máy bạn. Cần GEMINI_API_KEY."""
    from google import genai

    client = genai.Client()
    if model.startswith("imagen"):
        resp = client.models.generate_images(
            model=model, prompt=prompt,
            config=genai.types.GenerateImagesConfig(number_of_images=1, aspect_ratio="16:9"),
        )
        out.write_bytes(resp.generated_images[0].image.image_bytes)
        return out
    resp = client.models.generate_content(model=model, contents=f"{prompt}. Wide 16:9 landscape image, no text.")
    for part in resp.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            out.write_bytes(part.inline_data.data)
            return out
    raise RuntimeError(f"{model} không trả về ảnh")


def make_background(prompt: str, out: Path, cfg: dict, seed: int | None = None) -> Path:
    """image_engine: placeholder | comfyui (GPU máy bạn) | cloud (Google). Lỗi => dùng ảnh giữ chỗ để
    pipeline tự động không bị dừng."""
    comfy = cfg.get("comfyui") or {}
    engine = cfg.get("image_engine") or ("comfyui" if comfy.get("enabled") else "placeholder")
    try:
        if engine == "comfyui":
            from . import comfyui

            return comfyui.generate(prompt, out, comfy, seed=seed)
        if engine == "cloud":
            return cloud_image(prompt, out, cfg.get("cloud_image_model", "imagen-4.0-generate-001"))
    except Exception as e:
        print(f"  [ảnh] {engine} lỗi ({e}) — dùng ảnh giữ chỗ")
    return placeholder_background(prompt, out)


def _font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    for p in [path, *FALLBACK_FONTS]:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _fit_font(draw, lines, font_path, box_w, box_h, stroke_ratio=0.06):
    size = box_h // max(len(lines), 1)
    while size > 12:
        font = _font(font_path, size)
        stroke = max(2, int(size * stroke_ratio))
        widths = [draw.textbbox((0, 0), ln, font=font, stroke_width=stroke)[2] for ln in lines]
        height = sum(draw.textbbox((0, 0), ln, font=font, stroke_width=stroke)[3] for ln in lines)
        if max(widths) <= box_w and height * 1.1 <= box_h:
            return font, stroke
        size -= 4
    return _font(font_path, 12), 2


def compose(background: Path, lines: list[str], out: Path, cfg: dict) -> Path:
    W, H = cfg.get("size", [1280, 720])
    img = cover(Image.open(background).convert("RGB"), (W, H)).convert("RGBA")

    # Gradient tối ở vùng đặt chữ để chữ luôn nổi
    x0, y0, x1, y1 = [round(v * d) for v, d in zip(cfg["text_box"], (W, H, W, H))]
    bottom = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(bottom)
    for y in range(H):
        bd.line([(0, y), (W, y)], fill=int(210 * max(0.0, (y - H * 0.35) / (H * 0.65))))
    left = Image.new("L", (W, H), 0)
    ld = ImageDraw.Draw(left)
    for x in range(W):
        ld.line([(x, 0), (x, H)], fill=int(170 * max(0.0, 1 - x / (W * 0.7))))
    shade = ImageChops.lighter(bottom, left)
    img = Image.alpha_composite(img, Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [shade]))

    template = cfg.get("template")
    if template and Path(template).exists():
        frame = Image.open(template).convert("RGBA").resize((W, H))
        img = Image.alpha_composite(img, frame)

    lines = [ln.upper() for ln in lines if ln]
    draw = ImageDraw.Draw(img)
    font, stroke = _fit_font(draw, lines, cfg.get("font"), x1 - x0, y1 - y0)
    line_h = [draw.textbbox((0, 0), ln, font=font, stroke_width=stroke)[3] for ln in lines]
    y = y1 - int(sum(line_h) * 1.08)

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    yy = y
    for ln, lh in zip(lines, line_h):
        sdraw.text((x0 + 6, yy + 8), ln, font=font, fill=(0, 0, 0, 200))
        yy += int(lh * 1.08)
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(8)))

    draw = ImageDraw.Draw(img)
    for ln, lh in zip(lines, line_h):
        draw.text((x0, y), ln, font=font, fill=cfg["text_color"], stroke_width=stroke, stroke_fill=cfg["stroke_color"])
        y += int(lh * 1.08)

    badge = (cfg.get("badge") or "").strip()
    if badge:
        bfont = _font(cfg.get("font"), max(18, H // 22))
        pad_x, pad_y = H // 45, H // 90
        l, t, r, b = draw.textbbox((0, 0), badge, font=bfont)
        bx, by = x0, round(H * 0.05)
        draw.rounded_rectangle(
            (bx, by, bx + (r - l) + 2 * pad_x, by + (b - t) + 2 * pad_y),
            radius=pad_y * 2, fill=cfg.get("badge_color", "#B8322A"),
        )
        draw.text((bx + pad_x - l, by + pad_y - t), badge, font=bfont, fill=cfg.get("badge_text_color", "#FFFFFF"))

    img.convert("RGB").save(out, quality=92)
    return out


# ====================================================================== bố cục "split"
# Kiểu phổ biến của các kênh truyện audio Việt: 1 nửa là ảnh minh họa (khung bo góc, viền trắng),
# nửa còn lại là nền giấy sáng với TÊN TRUYỆN chữ đậm cỡ lớn, vài cụm từ được tô màu nổi bật,
# nhãn tên kênh/số tập ở trên và mascot của kênh ở góc.

def _paper(size, color: str) -> Image.Image:
    """Nền giấy: màu kem + nhiễu mịn để không phẳng lì."""
    import random

    W, H = size
    base = Image.new("RGB", size, color)
    noise = Image.effect_noise((W // 4, H // 4), 18).resize(size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(2))
    tint = Image.merge("RGB", [noise] * 3)
    paper = Image.blend(base, ImageChops.multiply(base, tint.point(lambda v: 200 + v // 5)), 0.35)
    d = ImageDraw.Draw(paper)
    dot = tuple(max(0, c - 18) for c in ImageColor.getrgb(color)[:3])  # chấm đậm hơn nền một chút
    rnd = random.Random(7)
    for _ in range(18):  # vài chấm mờ trang trí
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(2, 5)
        d.ellipse((x - r, y - r, x + r, y + r), fill=dot)
    return paper


def _framed_photo(img: Image.Image, size, radius: int, border: int) -> Image.Image:
    w, h = size
    photo = cover(img.convert("RGB"), (w - 2 * border, h - 2 * border))
    frame = Image.new("RGBA", size, (0, 0, 0, 0))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    frame.paste((255, 255, 255, 255), (0, 0), mask)
    inner = Image.new("L", photo.size, 0)
    ImageDraw.Draw(inner).rounded_rectangle((0, 0, photo.width - 1, photo.height - 1),
                                            radius=max(4, radius - border), fill=255)
    frame.paste(photo, (border, border), inner)
    return frame


def mark_highlights(words: list[str], phrases: list[str], colors: list[str], base: str) -> list[str]:
    """Trả về màu cho từng từ: từ nằm trong cụm highlight được tô màu (luân phiên theo cụm)."""
    out = [base] * len(words)
    norm = [w.upper().strip(",.!?:;") for w in words]
    for pi, phrase in enumerate(p for p in phrases if p):
        target = phrase.upper().split()
        n = len(target)
        for i in range(len(norm) - n + 1):
            if [t.strip(",.!?:;") for t in norm[i:i + n]] == [t.strip(",.!?:;") for t in target]:
                for j in range(i, i + n):
                    out[j] = colors[pi % len(colors)]
                break
    return out


def _units(words: list[str], colors: list[str], base: str) -> list[list[int]]:
    """Gom các từ liền nhau cùng màu highlight thành 1 khối không ngắt dòng (giữ "MỎ HỖN" trên 1 dòng)."""
    units: list[list[int]] = []
    for i, c in enumerate(colors):
        if units and c != base and colors[units[-1][-1]] == c:
            units[-1].append(i)
        else:
            units.append([i])
    return units


def _wrap(words, font, max_w, draw, units=None):
    space = draw.textlength(" ", font=font)
    units = units or [[i] for i in range(len(words))]
    lines, cur, cur_w = [], [], 0.0
    for unit in units:
        uw = sum(draw.textlength(words[i], font=font) for i in unit) + space * (len(unit) - 1)
        if cur and cur_w + space + uw > max_w:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur_w = cur_w + (space if cur else 0) + uw
        cur.extend(unit)
    if cur:
        lines.append(cur)
    return lines


def layout_title(draw, words, font_path, box_w, box_h, max_lines=4, line_gap=1.08, units=None):
    """Chọn cỡ chữ lớn nhất sao cho tên truyện vừa khung, rồi cân dòng cho đều (không dòng cụt)."""
    for size in range(int(box_h / 2.2), 18, -3):
        font = _font(font_path, size)
        lines = _wrap(words, font, box_w, draw, units)
        asc, desc = font.getmetrics()
        line_h = (asc + desc) * line_gap
        if len(lines) <= max_lines and line_h * len(lines) <= box_h:
            # Cân dòng: thu hẹp chiều rộng chừng nào số dòng chưa tăng
            width = box_w
            while width > box_w * 0.5:
                trial = _wrap(words, font, width * 0.94, draw, units)
                if len(trial) != len(lines):
                    break
                lines, width = trial, width * 0.94
            return font, lines, line_h
    font = _font(font_path, 18)
    return font, _wrap(words, font, box_w, draw, units), sum(font.getmetrics()) * line_gap


def compose_split(background: Path, title: str, highlights: list[str], out: Path, cfg: dict) -> Path:
    W, H = cfg.get("size", [1280, 720])
    canvas = _paper((W, H), cfg.get("paper_color", "#FBF4E6")).convert("RGBA")
    m = round(H * 0.06)
    img_w = round(W * cfg.get("image_ratio", 0.46))
    right = cfg.get("image_side", "left") == "right"
    img_x = W - img_w - m if right else m
    photo = _framed_photo(Image.open(background), (img_w, H - 2 * m), radius=round(H * 0.06), border=round(H * 0.014))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((img_x + 8, m + 12, img_x + img_w + 8, H - m + 12),
                                             radius=round(H * 0.06), fill=(60, 40, 20, 90))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(14)))
    canvas.alpha_composite(photo, (img_x, m))

    tx0 = m * 2 if right else img_x + img_w + m * 1.2
    tx1 = img_x - m * 1.2 if right else W - m * 1.5
    tx0, tx1 = round(tx0), round(tx1)
    draw = ImageDraw.Draw(canvas)

    # Nhãn tên kênh / số tập
    top = m
    badge = (cfg.get("badge") or "").strip()
    if badge:
        bfont = _font(cfg.get("badge_font") or cfg.get("font"), round(H * 0.052))
        l, t, r, b = draw.textbbox((0, 0), badge, font=bfont)
        pw, ph = round(H * 0.03), round(H * 0.016)
        bw, bh = (r - l) + 2 * pw, (b - t) + 2 * ph
        bx = (tx0 + tx1 - bw) // 2
        draw.rounded_rectangle((bx, top, bx + bw, top + bh), radius=bh // 2, fill=cfg.get("badge_color", "#F6E3A1"))
        draw.text((bx + pw - l, top + ph - t), badge, font=bfont, fill=cfg.get("badge_text_color", "#4A2A12"))
        top += bh + round(H * 0.04)

    # Tên truyện
    words = title.upper().split()
    base = cfg.get("title_color", "#3A1E12")
    colors = mark_highlights(words, list(highlights or []), cfg.get("highlight_colors", ["#C62828", "#2E7D32"]), base)
    box_h = H - top - m * 1.6
    font, lines, line_h = layout_title(draw, words, cfg.get("font"), tx1 - tx0, box_h, cfg.get("max_lines", 4),
                                       units=_units(words, colors, base))
    space = draw.textlength(" ", font=font)
    y = top + (box_h - line_h * len(lines)) / 2
    for line in lines:
        lw = sum(draw.textlength(words[i], font=font) for i in line) + space * (len(line) - 1)
        x = (tx0 + tx1 - lw) / 2
        for i in line:
            draw.text((x + 3, y + 4), words[i], font=font, fill=(0, 0, 0, 45))  # bóng nhẹ
            draw.text((x, y), words[i], font=font, fill=colors[i])
            x += draw.textlength(words[i], font=font) + space
        y += line_h

    for key, anchor in (("template", None), ("mascot", "corner")):
        path = cfg.get(key)
        if path and Path(path).exists():
            layer = Image.open(path).convert("RGBA")
            if anchor == "corner":  # mascot: góc trên, phía khối chữ
                layer.thumbnail((round(H * 0.22), round(H * 0.22)))
                pos = (round(tx1 - layer.width * 0.6), round(m * 0.3)) if not right else (round(tx0 - layer.width * 0.4), round(m * 0.3))
                canvas.alpha_composite(layer, pos)
            else:
                canvas = Image.alpha_composite(canvas, layer.resize((W, H)))

    canvas.convert("RGB").save(out, quality=92)
    return out


def render_thumbnail(background: Path, meta: dict, out: Path, cfg: dict) -> Path:
    """Chọn bố cục theo thumbnail.layout: split (tên truyện + ảnh) | overlay (chữ đè lên ảnh)."""
    if cfg.get("layout", "split") == "split":
        title = meta.get("story_title") or " ".join(meta.get("thumb_text", []))
        return compose_split(background, title, meta.get("thumb_highlight", []), out, cfg)
    return compose(background, meta["thumb_text"], out, cfg)
