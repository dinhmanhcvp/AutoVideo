"""Client Telegram Bot API tối giản (requests, không cần thư viện bot)."""
from __future__ import annotations

import json
import os
from pathlib import Path

API = "https://api.telegram.org/bot{token}/{method}"


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | int | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = str(chat_id or os.environ.get("TELEGRAM_CHAT_ID", ""))
        if not self.token:
            raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN (tạo bot qua @BotFather)")

    def call(self, method: str, files: dict | None = None, timeout: float = 120, **params):
        import requests

        data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in params.items() if v is not None}
        handles = {k: open(v, "rb") for k, v in (files or {}).items()}
        try:
            resp = requests.post(API.format(token=self.token, method=method), data=data, files=handles or None,
                                 timeout=timeout)
        finally:
            for h in handles.values():
                h.close()
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method} lỗi: {body.get('description')}")
        return body["result"]

    # ---- gửi
    def text(self, text: str, buttons=None, chat_id=None, **kw):
        return self.call("sendMessage", chat_id=chat_id or self.chat_id, text=text[:4096],
                         reply_markup=keyboard(buttons), disable_web_page_preview=True, **kw)

    def photo(self, path: Path, caption: str = "", buttons=None):
        return self.call("sendPhoto", files={"photo": path}, chat_id=self.chat_id, caption=caption[:1024],
                         reply_markup=keyboard(buttons))

    def video(self, path: Path, caption: str = "", buttons=None):
        return self.call("sendVideo", files={"video": path}, chat_id=self.chat_id, caption=caption[:1024],
                         supports_streaming=True, reply_markup=keyboard(buttons), timeout=600)

    def edit_buttons(self, message_id: int, buttons=None):
        return self.call("editMessageReplyMarkup", chat_id=self.chat_id, message_id=message_id,
                         reply_markup=keyboard(buttons) or {"inline_keyboard": []})

    def answer(self, callback_id: str, text: str = ""):
        return self.call("answerCallbackQuery", callback_query_id=callback_id, text=text[:200])

    def updates(self, offset: int | None, timeout: int = 50):
        """Long polling: chờ tối đa `timeout` giây phía server Telegram."""
        import requests

        resp = requests.post(
            API.format(token=self.token, method="getUpdates"),
            data={"offset": offset, "timeout": timeout,
                  "allowed_updates": json.dumps(["message", "callback_query"])},
            timeout=timeout + 15,
        )
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram getUpdates lỗi: {body.get('description')}")
        return body["result"]


def keyboard(buttons):
    """buttons: [[(label, callback_data), ...], ...] -> inline_keyboard."""
    if not buttons:
        return None
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
