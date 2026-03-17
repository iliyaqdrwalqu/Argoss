"""
whatsapp_bridge.py — WhatsApp Cloud API мост с fallback на Twilio WhatsApp.
"""
from __future__ import annotations

import os
from typing import Any

import requests


class WhatsAppBridge:
    def __init__(
        self,
        cloud_token: str | None = None,
        phone_number_id: str | None = None,
        api_version: str | None = None,
        twilio_account_sid: str | None = None,
        twilio_auth_token: str | None = None,
        twilio_whatsapp_from: str | None = None,
        timeout: float = 10.0,
    ):
        self.cloud_token = cloud_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.api_version = api_version or os.getenv("WHATSAPP_API_VERSION", "v20.0")

        self.twilio_account_sid = twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_whatsapp_from = twilio_whatsapp_from or os.getenv("TWILIO_WHATSAPP_FROM", "")
        self.timeout = timeout

    def _cloud_ready(self) -> bool:
        return bool(self.cloud_token and self.phone_number_id)

    def _twilio_ready(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_whatsapp_from)

    def send_message(self, to: str, text: str) -> dict[str, Any]:
        cloud_error = ""
        if self._cloud_ready():
            try:
                return self._send_via_cloud_api(to=to, text=text)
            except Exception as exc:  # pragma: no cover - exercised through tests with mocking
                cloud_error = str(exc)

        if self._twilio_ready():
            try:
                return self._send_via_twilio(to=to, text=text)
            except Exception as exc:  # pragma: no cover - exercised through tests with mocking
                return {"ok": False, "provider": "twilio", "error": str(exc)}

        if cloud_error:
            return {"ok": False, "provider": "whatsapp_cloud", "error": cloud_error}
        return {"ok": False, "provider": "none", "error": "Bridge is not configured"}

    def _send_via_cloud_api(self, to: str, text: str) -> dict[str, Any]:
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.cloud_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return {"ok": True, "provider": "whatsapp_cloud", "data": response.json()}

    def _send_via_twilio(self, to: str, text: str) -> dict[str, Any]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
        from_value = self.twilio_whatsapp_from
        if not from_value.startswith("whatsapp:"):
            from_value = f"whatsapp:{from_value}"
        to_value = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        payload = {
            "From": from_value,
            "To": to_value,
            "Body": text,
        }
        response = requests.post(
            url,
            data=payload,
            auth=(self.twilio_account_sid, self.twilio_auth_token),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return {"ok": True, "provider": "twilio", "data": response.json()}
