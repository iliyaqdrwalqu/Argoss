"""
slack_bridge.py — Slack bridge с поддержкой Socket Mode (Bolt) и Web API.
"""
from __future__ import annotations

import os
from typing import Any

import requests


class SlackBridge:
    def __init__(
        self,
        bot_token: str | None = None,
        app_token: str | None = None,
        default_channel: str | None = None,
        timeout: float = 10.0,
    ):
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN", "")
        self.app_token = app_token or os.getenv("SLACK_APP_TOKEN", "")
        self.default_channel = default_channel or os.getenv("SLACK_DEFAULT_CHANNEL", "")
        self.timeout = timeout

    def socket_mode_ready(self) -> bool:
        return bool(self.bot_token and self.app_token)

    def send_message(self, text: str, channel: str | None = None) -> dict[str, Any]:
        target_channel = channel or self.default_channel
        if not self.bot_token:
            return {"ok": False, "provider": "slack", "error": "SLACK_BOT_TOKEN is not configured"}
        if not target_channel:
            return {"ok": False, "provider": "slack", "error": "Slack channel is required"}

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {"channel": target_channel, "text": text}
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            return {"ok": False, "provider": "slack", "error": data.get("error", "unknown_error"), "data": data}
        return {"ok": True, "provider": "slack", "data": data}
