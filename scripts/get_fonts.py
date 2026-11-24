"""Tải font chữ hỗ trợ tiếng Việt (Google Fonts, giấy phép OFL) vào assets/fonts/.

    python scripts/get_fonts.py

- Anton:   chữ đậm, hẹp, cao — kiểu tiêu đề thumbnail truyện audio phổ biến.
- Baloo2:  chữ tròn, dễ thương — hợp truyện hài, ngôn tình nhẹ nhàng.
- Oswald:  đậm vừa, hẹp — dùng cho nhãn/badge.
"""
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {
    "Anton-Regular.ttf": "anton/Anton-Regular.ttf",
    "Baloo2.ttf": "baloo2/Baloo2%5Bwght%5D.ttf",
    "Oswald.ttf": "oswald/Oswald%5Bwght%5D.ttf",
}

out_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
out_dir.mkdir(parents=True, exist_ok=True)
for name, path in FONTS.items():
    dest = out_dir / name
    if dest.exists():
        print(f"đã có  {dest.name}")
        continue
    with urllib.request.urlopen(BASE + path, timeout=60) as resp:
        dest.write_bytes(resp.read())
    print(f"đã tải {dest.name}")
