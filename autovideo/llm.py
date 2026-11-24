"""Lớp mỏng gọi LLM: Anthropic (Claude) hoặc Google Gemini, cùng một giao diện complete()."""
from __future__ import annotations

import json
import re


class LLMError(RuntimeError):
    pass


class AnthropicLLM:
    def __init__(self, model: str, effort: str = "medium"):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()  # đọc ANTHROPIC_API_KEY / profile `ant auth login`
        self.model = model
        self.effort = effort

    def complete(self, system: str, user: str, max_tokens: int = 32000) -> str:
        # Streaming để tránh timeout với đầu ra dài (bản dịch cả chương).
        # fallbacks="default": nếu model từ chối (stop_reason=refusal), server tự chạy lại
        # trên model dự phòng phù hợp — hữu ích với truyện có cảnh bạo lực/kiếm hiệp.
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise LLMError(f"Model từ chối xử lý đoạn này: {msg.stop_details}")
        if msg.stop_reason == "max_tokens":
            raise LLMError("Đầu ra bị cắt do max_tokens — giảm llm.source_chunk_chars")
        return "".join(b.text for b in msg.content if b.type == "text").strip()


class GeminiLLM:
    def __init__(self, model: str, **_):
        from google import genai

        self._types = genai.types
        self.client = genai.Client()  # đọc GEMINI_API_KEY
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 32000) -> str:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=user,
            config=self._types.GenerateContentConfig(
                system_instruction=system, max_output_tokens=max_tokens
            ),
        )
        if not resp.text:
            raise LLMError(f"Gemini không trả về text: {resp}")
        return resp.text.strip()


def make_llm(cfg: dict):
    provider = cfg["provider"].lower()
    if provider == "anthropic":
        return AnthropicLLM(cfg["model"], cfg.get("effort", "medium"))
    if provider == "gemini":
        return GeminiLLM(cfg["model"])
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
