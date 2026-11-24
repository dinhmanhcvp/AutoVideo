"""Module 4: ảnh nền (ComfyUI hoặc ảnh giữ chỗ) + đóng khung thumbnail đồng bộ nhận diện kênh."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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
        draw.text((bx + pad_x - l, by + pad_y - t), badge, font=bfont, fill="#FFFFFF")

    img.convert("RGB").save(out, quality=92)
    return out
