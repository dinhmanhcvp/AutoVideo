"""Lớp mỏng gọi LLM: Anthropic (Claude) hoặc Google Gemini, cùng một giao diện complete().

- doc=...: văn bản dài dùng chung cho nhiều lần gọi (toàn văn truyện). Với Claude, khối này được đặt
  ĐẦU TIÊN và đánh dấu prompt caching => các lần gọi sau (metadata, hook, chương...) chỉ trả ~5–10%
  giá cho phần truyện. Vì vậy system prompt khi có doc được giữ cố định, chỉ dẫn từng việc nằm sau doc.
- usage: cộng dồn token và ước tính chi phí (USD) để ghi vào cost.json của từng video.
"""
from __future__ import annotations

import json
import re

# Giá USD / 1 triệu token: (input, output, cache_read, cache_write)
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}

DOC_SYSTEM = ("Bạn là biên tập viên văn học và biên kịch cho một kênh truyện audio tiếng Việt trên YouTube. "
              "Làm đúng nhiệm vụ được giao sau phần văn bản, đúng định dạng yêu cầu.")


class LLMError(RuntimeError):
    pass


class Usage:
    def __init__(self, model: str, price=None):
        self.model = model
        self.price = tuple(price) if price else PRICES.get(model, (0, 0, 0, 0))
        self.data = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                     "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}

    def add(self, **tokens):
        self.data["calls"] += 1
        for k, v in tokens.items():
            self.data[k] = self.data.get(k, 0) + (v or 0)

    @property
    def usd(self) -> float:
        pi, po, pr, pw = self.price
        d = self.data
        return round((d["input_tokens"] * pi + d["output_tokens"] * po + d["cache_read_input_tokens"] * pr
                      + d["cache_creation_input_tokens"] * pw) / 1e6, 4)

    def snapshot(self) -> dict:
        return {"model": self.model, **self.data, "usd": self.usd}


class AnthropicLLM:
    def __init__(self, model: str, effort: str = "medium", price=None):
        import anthropic

        self.client = anthropic.Anthropic()  # đọc ANTHROPIC_API_KEY / profile `ant auth login`
        self.model = model
        self.effort = effort
        self.usage = Usage(model, price)

    def complete(self, system: str, user: str, max_tokens: int = 32000, doc: str | None = None) -> str:
        if doc:
            sys_prompt = DOC_SYSTEM
            content = [
                {"type": "text", "text": doc, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": f"<nhiem_vu>\n{system}\n</nhiem_vu>\n\n{user}".strip()},
            ]
        else:
            sys_prompt, content = system, user
        # Streaming: tránh timeout với đầu ra dài. fallbacks="default": nếu model từ chối
        # (stop_reason=refusal), server tự chạy lại trên model dự phòng phù hợp.
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=sys_prompt,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
        u = msg.usage
        self.usage.add(input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                       cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0),
                       cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0))
        if msg.stop_reason == "refusal":
            raise LLMError(f"Model từ chối xử lý đoạn này: {msg.stop_details}")
        if msg.stop_reason == "max_tokens":
            raise LLMError("Đầu ra bị cắt do max_tokens — giảm llm.source_chunk_chars")
        return "".join(b.text for b in msg.content if b.type == "text").strip()


class GeminiLLM:
    def __init__(self, model: str, price=None, **_):
        from google import genai

        self._types = genai.types
        self.client = genai.Client()  # đọc GEMINI_API_KEY
        self.model = model
        self.usage = Usage(model, price)

    def complete(self, system: str, user: str, max_tokens: int = 32000, doc: str | None = None) -> str:
        contents = f"{doc}\n\n{user}" if doc else user
        resp = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
        )
        meta = getattr(resp, "usage_metadata", None)
        self.usage.add(input_tokens=getattr(meta, "prompt_token_count", 0),
                       output_tokens=getattr(meta, "candidates_token_count", 0))
        if not resp.text:
            raise LLMError(f"Gemini không trả về text: {resp}")
        return resp.text.strip()


def make_llm(cfg: dict):
    provider = cfg["provider"].lower()
    if provider == "anthropic":
        return AnthropicLLM(cfg["model"], cfg.get("effort", "medium"), cfg.get("price"))
    if provider == "gemini":
        return GeminiLLM(cfg["model"], cfg.get("price"))
    raise ValueError(f"llm.provider không hỗ trợ: {provider}")


def extract_json(text: str) -> dict:
    """Lấy object JSON đầu tiên trong câu trả lời (chịu được ```json ... ``` hoặc lời dẫn thừa)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    if start < 0:
        raise LLMError(f"Không tìm thấy JSON trong: {text[:200]}")
    obj, _ = json.JSONDecoder().raw_decode(candidate[start:])
    return obj
