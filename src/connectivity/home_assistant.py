"""
home_assistant.py — Интеграция Аргоса с Home Assistant
  Поддержка:
  - REST API (states/services)
  - MQTT publish (опционально)
"""
import json
import os
from typing import Any

import requests

from src.argos_logger import get_logger

log = get_logger("argos.ha")


class HomeAssistantBridge:
    def __init__(self):
        self.base_url = os.getenv("HA_URL", "http://localhost:8123").rstrip("/")
        self.token = os.getenv("HA_TOKEN", "").strip()
        self.mqtt_host = os.getenv("HA_MQTT_HOST", "localhost").strip()
        self.mqtt_port = int(os.getenv("HA_MQTT_PORT", "1883"))
        self._mqtt = None

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def health(self) -> str:
        if not self.enabled:
            return "⚠️ Home Assistant: не настроен (укажи HA_URL и HA_TOKEN)."
        try:
            r = requests.get(f"{self.base_url}/api/", headers=self._headers(), timeout=5)
            if r.ok:
                return f"✅ Home Assistant API: {self.base_url}"
            return f"❌ Home Assistant API: HTTP {r.status_code}"
        except Exception as e:
            return f"❌ Home Assistant API: {e}"

    def list_states(self, limit: int = 20) -> str:
        if not self.enabled:
            return "⚠️ Home Assistant: не настроен."
        try:
            r = requests.get(f"{self.base_url}/api/states", headers=self._headers(), timeout=10)
            if not r.ok:
                return f"❌ HA states HTTP {r.status_code}"
            states = r.json()[:max(1, min(limit, 100))]
            lines = [f"🏠 Home Assistant состояния ({len(states)}):"]
            for s in states:
                lines.append(f"  • {s.get('entity_id','?')} = {s.get('state','?')}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ HA states: {e}"

    def call_service(self, domain: str, service: str, data: dict[str, Any] | None = None) -> str:
        if not self.enabled:
            return "⚠️ Home Assistant: не настроен."
        payload = data or {}
        try:
            r = requests.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self._headers(),
                data=json.dumps(payload, ensure_ascii=False),
                timeout=10,
            )
            if r.ok:
                return f"✅ HA service: {domain}.{service}"
            return f"❌ HA service HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return f"❌ HA service: {e}"

    def _connect_mqtt(self):
        if self._mqtt:
            return True, ""
        try:
            import paho.mqtt.client as mqtt

            client = mqtt.Client()
            client.connect(self.mqtt_host, self.mqtt_port, 60)
            client.loop_start()
            self._mqtt = client
            return True, ""
        except Exception as e:
            return False, str(e)

    def publish_mqtt(self, topic: str, payload: dict[str, Any] | str) -> str:
        ok, err = self._connect_mqtt()
        if not ok:
            return f"❌ HA MQTT: {err}"
        try:
            msg = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            self._mqtt.publish(topic, msg)
            return f"✅ HA MQTT → {topic}: {str(msg)[:80]}"
        except Exception as e:
            return f"❌ HA MQTT publish: {e}"
