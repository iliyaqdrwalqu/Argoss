"""
max_bridge.py — мост к Mail.ru MAX Bot API.
"""
from __future__ import annotations

import os
from typing import Any

import requests


class MaxBridge:
    def __init__(
        self,
        bot_token: str | None = None,
        api_base: str | None = None,
        timeout: float = 10.0,
    ):
        self.bot_token = bot_token or os.getenv("MAX_BOT_TOKEN", "")
        self.api_base = (api_base or os.getenv("MAX_BOT_API_BASE", "https://botapi.max.ru")).rstrip("/")
        self.timeout = timeout

    def _ready(self) -> bool:
        return bool(self.bot_token)

    def send_message(self, chat_id: str | int, text: str) -> dict[str, Any]:
        if not self._ready():
            return {"ok": False, "provider": "max", "error": "MAX_BOT_TOKEN is not configured"}

        url = f"{self.api_base}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return {"ok": True, "provider": "max", "data": response.json()}
