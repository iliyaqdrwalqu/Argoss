"""
shodan_scanner.py — Интеграция с Shodan API для сканирования сети.
"""
from __future__ import annotations

import os
from typing import Any

import requests

SHODAN_API_BASE = "https://api.shodan.io"


class ShodanScanner:
    """Клиент для Shodan API (REST, без зависимости от пакета shodan)."""

    def __init__(self, api_key: str | None = None, timeout: float = 15.0):
        self.api_key = api_key or os.getenv("SHODAN_API_KEY", "")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            return {"error": "SHODAN_API_KEY is not configured"}
        p = {"key": self.api_key, **(params or {})}
        resp = requests.get(f"{SHODAN_API_BASE}{path}", params=p, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def search(self, query: str, page: int = 1) -> dict[str, Any]:
        """Поиск устройств по запросу Shodan."""
        return self._get("/shodan/host/search", {"query": query, "page": page})

    def host_info(self, ip: str) -> dict[str, Any]:
        """Информация о конкретном IP-адресе."""
        return self._get(f"/shodan/host/{ip}")

    def my_ip(self) -> str:
        """Внешний IP текущего хоста по данным Shodan."""
        try:
            resp = requests.get(
                f"{SHODAN_API_BASE}/tools/myip",
                params={"key": self.api_key},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as exc:  # noqa: BLE001
            return f"error: {exc}"

    def api_info(self) -> dict[str, Any]:
        """Информация о плане и лимитах API-ключа."""
        return self._get("/api-info")

    def is_configured(self) -> bool:
        """Возвращает True если API-ключ задан."""
        return bool(self.api_key)
