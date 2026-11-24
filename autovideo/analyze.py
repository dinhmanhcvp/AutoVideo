"""Cổng chất lượng trước khi dịch: chấm điểm truyện (có đáng làm không) + dựng bảng nhân vật/thuật ngữ
để bản dịch nhất quán. Một lần gọi LLM rẻ, tránh tốn tiền dịch/đọc/render cho truyện yếu hoặc dở dang."""
from __future__ import annotations

import re

from .llm import extract_json
from .translate import fill, load_prompt

WEIGHTS = {"hook": 0.25, "premise": 0.2, "twist": 0.2, "emotion": 0.15, "pacing": 0.1, "vn_fit": 0.1}
GENRE_NAMES = {
    "co_trang": "cổ trang / tu tiên", "hien_dai": "ngôn tình hiện đại",
    "ngon_tinh": "ngôn tình hiện đại – hôn nhân hào môn, tổng tài", "tam_su": "tâm sự đời thực",
    "kinh_di": "kinh dị", "hai_huoc": "hài gia đình", "pha_an": "phá án / trinh thám",
}
_CJK = re.compile(r"[一-鿿]")
_VI = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.I)


class StoryRejected(Exception):
    """Truyện không qua cổng chất lượng — pipeline tự động bỏ qua, không tính là lỗi."""


def detect_language(text: str) -> str:
    sample = text[:5000]
    cjk, vi = len(_CJK.findall(sample)), len(_VI.findall(sample))
    if cjk > len(sample) * 0.2:
        return "zh"
    if vi > 20:
        return "vi"
    return "other"


def weighted_score(scores: dict) -> float:
    total = sum(WEIGHTS[k] * float(scores.get(k, 0) or 0) for k in WEIGHTS)
    return round(total, 2)


def analyze(llm, text: str, cfg: dict) -> dict:
    system = fill(load_prompt("analyze.md"), channel_name=cfg["channel"]["name"],
                  genre_name=GENRE_NAMES.get(cfg["genre"], cfg["genre"]))
    data = extract_json(llm.complete(system, "", max_tokens=8000, doc=f"<truyen>\n{text}\n</truyen>"))
    data["score"] = weighted_score(data.get("scores", {}))
    data["chars"] = len(text)
    return data


def verdict(report: dict, cfg: dict) -> str | None:
    """None = đạt; ngược lại là lý do loại."""
    q = cfg.get("quality", {})
    if q.get("require_complete", True) and report.get("complete") is False:
        return "truyện không trọn vẹn (chỉ là 1 tập/đoạn)"
    if q.get("require_ad_safe", True) and report.get("ad_safe") is False:
        return "không an toàn quảng cáo: " + ", ".join(report.get("red_flags", [])[:3])
    if report["score"] < q.get("min_score", 6.5):
        return f"điểm {report['score']} < {q.get('min_score', 6.5)}"
    if report.get("chars", 0) < q.get("min_chars", 3000):
        return f"truyện quá ngắn ({report.get('chars')} ký tự)"
    return None


def story_glossary(report: dict) -> dict:
    """Bảng Trung→Việt cho riêng truyện này (nhân vật + thuật ngữ)."""
    gl = {c["zh"]: c["vi"] for c in report.get("characters", []) if c.get("zh") and c.get("vi")}
    gl.update({k: v for k, v in (report.get("glossary") or {}).items() if k and v})
    return gl


def character_notes(report: dict) -> str:
    lines = []
    for c in report.get("characters", []):
        bits = [c.get("vi") or c.get("zh", "")]
        for k in ("gender", "role", "relations"):
            if c.get(k):
                bits.append(str(c[k]))
        lines.append("- " + " · ".join(bits))
    if report.get("pronoun_notes"):
        lines.append("Xưng hô: " + report["pronoun_notes"])
    return "\n".join(lines)
