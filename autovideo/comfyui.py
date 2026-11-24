"""Gọi ComfyUI local qua HTTP API để vẽ ảnh nền (Flux.1 / SDXL...).

Workflow phải được export bằng "Save (API Format)". Đặt chuỗi {{PROMPT}} vào ô text của node
CLIPTextEncode (positive); {{SEED}} (tùy chọn) vào ô seed của KSampler. Kích thước ảnh cấu hình
trong workflow (khuyến nghị 1344x768 hoặc 1920x1088 cho 16:9).
"""
from __future__ import annotations

import json
import random
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def _inject(node, prompt: str, seed: int):
    if isinstance(node, dict):
        return {k: _inject(v, prompt, seed) for k, v in node.items()}
    if isinstance(node, list):
        return [_inject(v, prompt, seed) for v in node]
    if node == "{{SEED}}":
        return seed
    if isinstance(node, str) and "{{PROMPT}}" in node:
        return node.replace("{{PROMPT}}", prompt)
    return node


def generate(prompt: str, out: Path, cfg: dict, seed: int | None = None) -> Path:
    base = cfg["url"].rstrip("/")
    workflow = json.loads(Path(cfg["workflow"]).read_text(encoding="utf-8"))
    graph = _inject(workflow, prompt, seed if seed is not None else random.randint(0, 2**31))
    body = json.dumps({"prompt": graph, "client_id": str(uuid.uuid4())}).encode()
    req = urllib.request.Request(f"{base}/prompt", data=body, headers={"Content-Type": "application/json"})
    prompt_id = json.load(urllib.request.urlopen(req))["prompt_id"]

    deadline = time.time() + cfg.get("timeout", 600)
    while time.time() < deadline:
        hist = json.load(urllib.request.urlopen(f"{base}/history/{prompt_id}"))
        if prompt_id in hist:
            for node_out in hist[prompt_id]["outputs"].values():
                for img in node_out.get("images", []):
                    q = urllib.parse.urlencode(
                        {"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img["type"]}
                    )
                    out.write_bytes(urllib.request.urlopen(f"{base}/view?{q}").read())
                    return out
            raise RuntimeError(f"ComfyUI chạy xong nhưng không có ảnh đầu ra (prompt {prompt_id})")
        time.sleep(2)
    raise TimeoutError(f"ComfyUI quá thời gian cho prompt {prompt_id}")
