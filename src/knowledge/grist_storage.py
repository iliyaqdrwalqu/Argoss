"""
grist_storage.py — ARGOS Grist P2P Distributed Storage.

Grist (https://getgrist.com / self-hosted) — открытая таблично-реляционная БД
с REST API. Используется как P2P-хранилище: каждая нода пишет/читает данные
через общий Grist-документ, обеспечивая синхронизацию состояния кластера.

Возможности:
  • Хранение данных памяти (факты, заметки, ключи) в Grist-таблицах
  • P2P-синхронизация: ноды пишут в общий документ, читают записи других нод
  • Автоматическое создание таблиц при первом запуске
  • Шифрование значений через ГОСТ Кузнечик-CTR перед записью

Переменные окружения:
  GRIST_API_KEY      — ключ API Grist (Settings → API key)
  GRIST_SERVER_URL   — URL сервера (по умолчанию https://docs.getgrist.com)
  GRIST_DOC_ID       — ID документа (из URL: /doc/<DOC_ID>, alias: GIST_ID)
  GRIST_ENCRYPT      — on/off шифрование ГОСТ (по умолчанию on)

Команды ядра:
  grist статус                  — состояние подключения
  grist сохрани [ключ] [значение]  — сохранить запись
  grist получи [ключ]           — получить запись
  grist список                  — все записи ноды
  grist синк                    — синхронизировать с другими нодами
  grist таблицы                 — список таблиц документа
"""
from __future__ import annotations

import json
import os
import socket
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.argos_logger import get_logger

log = get_logger("argos.grist")

try:
    import requests as _req
    REQUESTS_OK = True
except ImportError:
    _req = None
    REQUESTS_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────────────────────────────────────
GRIST_SERVER  = os.getenv("GRIST_SERVER_URL", "https://docs.getgrist.com").rstrip("/")
GRIST_API_KEY = os.getenv("GRIST_API_KEY", "")
GRIST_DOC_ID  = os.getenv("GRIST_DOC_ID") or os.getenv("GIST_ID", "8e9cf57e043c7a6111f277828f363b01")
GRIST_ENCRYPT = os.getenv("GRIST_ENCRYPT", "on").lower() not in {"0", "off", "false", "нет"}

# Имена таблиц в Grist-документе
TABLE_STORE   = "ArgosStore"       # ключ-значение хранилище нод
TABLE_NODES   = "ArgosNodes"       # реестр P2P-нод
TABLE_EVENTS  = "ArgosEvents"      # события (логи, алерты)


# ─────────────────────────────────────────────────────────────────────────────
# Клиент Grist REST API
# ─────────────────────────────────────────────────────────────────────────────

class GristClient:
    """Тонкий клиент Grist REST API v1."""

    def __init__(self, server: str, api_key: str, doc_id: str):
        self.server  = server.rstrip("/")
        self.api_key = api_key
        self.doc_id  = doc_id
        self._base   = f"{self.server}/api/docs/{doc_id}"

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    def _get(self, path: str, params: dict = None) -> dict:
        if not REQUESTS_OK:
            raise RuntimeError("requests не установлен: pip install requests")
        r = _req.get(f"{self._base}{path}", headers=self._headers,
                     params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        if not REQUESTS_OK:
            raise RuntimeError("requests не установлен")
        r = _req.post(f"{self._base}{path}", headers=self._headers,
                      json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        if not REQUESTS_OK:
            raise RuntimeError("requests не установлен")
        r = _req.patch(f"{self._base}{path}", headers=self._headers,
                       json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    # ── Таблицы ──────────────────────────────────────────────────────────────

    def list_tables(self) -> List[str]:
        """Список таблиц документа."""
        data = self._get("/tables")
        return [t["id"] for t in data.get("tables", [])]

    def create_table(self, table_id: str, columns: List[dict]) -> bool:
        """Создаёт таблицу если её нет."""
        existing = self.list_tables()
        if table_id in existing:
            return False
        self._post("/tables", {
            "tables": [{
                "id": table_id,
                "columns": columns,
            }]
        })
        log.info("Grist: создана таблица %s", table_id)
        return True

    # ── Записи ───────────────────────────────────────────────────────────────

    def fetch_rows(self, table_id: str, filters: dict = None) -> List[dict]:
        """Возвращает строки таблицы (с опциональным фильтром по колонкам)."""
        params = {}
        if filters:
            params["filter"] = json.dumps(filters)
        data = self._get(f"/tables/{table_id}/records", params=params)
        records = data.get("records", [])
        # Grist возвращает {id, fields: {...}}
        return [{"_id": r["id"], **r["fields"]} for r in records]

    def add_row(self, table_id: str, fields: dict) -> int:
        """Добавляет строку, возвращает rowId."""
        data = self._post(f"/tables/{table_id}/records",
                          {"records": [{"fields": fields}]})
        ids = data.get("records", [{}])
        return ids[0].get("id", -1) if ids else -1

    def update_row(self, table_id: str, row_id: int, fields: dict) -> bool:
        """Обновляет строку по ID."""
        self._patch(f"/tables/{table_id}/records",
                    {"records": [{"id": row_id, "fields": fields}]})
        return True

    def ping(self) -> bool:
        """Проверяет доступность API."""
        try:
            self._get("/tables")
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Основной класс хранилища
# ─────────────────────────────────────────────────────────────────────────────

class GristStorage:
    """
    P2P-хранилище на основе Grist.

    Каждая нода Аргоса пишет свои данные в общий Grist-документ,
    доступный всем нодам кластера. Обеспечивает:
    - Хранение ключ-значение
    - Обнаружение других нод
    - Синхронизацию событий и алертов
    - Опциональное ГОСТ-шифрование значений
    """

    def __init__(self, server: str = GRIST_SERVER,
                 api_key: str = GRIST_API_KEY,
                 doc_id: str = GRIST_DOC_ID,
                 encrypt: bool = GRIST_ENCRYPT):
        self._configured = bool(api_key and doc_id)
        self._encrypt    = encrypt
        self._node_id    = self._get_node_id()
        self._gost       = None

        if not self._configured:
            log.info("Grist: не настроен (нет GRIST_API_KEY / GRIST_DOC_ID)")
            return

        self._client = GristClient(server, api_key, doc_id)

        # ГОСТ-шифрование
        if encrypt:
            try:
                from src.connectivity.gost_p2p import GostP2PSecurity
                secret = os.getenv("ARGOS_NETWORK_SECRET", "argos_grist_default")
                self._gost = GostP2PSecurity(secret=secret, cipher="kuznyechik")
                log.info("Grist: ГОСТ-шифрование активировано")
            except Exception as e:
                log.warning("Grist ГОСТ: %s", e)

        # Создаём таблицы при первом запуске
        try:
            self._ensure_tables()
        except Exception as e:
            log.warning("Grist ensure_tables: %s", e)

    # ── Инициализация ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_node_id() -> str:
        path = os.path.join("config", "node_id")
        if os.path.exists(path):
            with open(path) as f:
                return f.read().strip()
        return socket.gethostname()

    def _ensure_tables(self):
        """Создаёт нужные таблицы в Grist-документе если их нет."""
        # ArgosStore: ключ-значение
        self._client.create_table(TABLE_STORE, [
            {"id": "node_id",    "fields": {"label": "Node ID",   "type": "Text"}},
            {"id": "key",        "fields": {"label": "Key",        "type": "Text"}},
            {"id": "value",      "fields": {"label": "Value",      "type": "Text"}},
            {"id": "encrypted",  "fields": {"label": "Encrypted",  "type": "Bool"}},
            {"id": "updated_at", "fields": {"label": "Updated At", "type": "Text"}},
        ])
        # ArgosNodes: реестр нод
        self._client.create_table(TABLE_NODES, [
            {"id": "node_id",   "fields": {"label": "Node ID",   "type": "Text"}},
            {"id": "hostname",  "fields": {"label": "Hostname",  "type": "Text"}},
            {"id": "ip",        "fields": {"label": "IP",        "type": "Text"}},
            {"id": "port",      "fields": {"label": "Port",      "type": "Int"}},
            {"id": "version",   "fields": {"label": "Version",   "type": "Text"}},
            {"id": "seen_at",   "fields": {"label": "Seen At",   "type": "Text"}},
            {"id": "gost",      "fields": {"label": "GOST",      "type": "Bool"}},
        ])
        # ArgosEvents: события
        self._client.create_table(TABLE_EVENTS, [
            {"id": "node_id",  "fields": {"label": "Node ID",  "type": "Text"}},
            {"id": "event",    "fields": {"label": "Event",    "type": "Text"}},
            {"id": "data",     "fields": {"label": "Data",     "type": "Text"}},
            {"id": "ts",       "fields": {"label": "Timestamp","type": "Text"}},
        ])

    # ── Шифрование значений ───────────────────────────────────────────────────

    def _enc(self, value: str) -> tuple[str, bool]:
        """Шифрует значение ГОСТ если включено. Возвращает (value_str, encrypted)."""
        if self._gost and self._encrypt:
            try:
                ct = self._gost.encrypt({"v": value})
                return ct.hex(), True
            except Exception as e:
                log.debug("Grist encrypt: %s", e)
        return value, False

    def _dec(self, value: str, encrypted: bool) -> str:
        """Дешифрует значение ГОСТ если зашифровано."""
        if encrypted and self._gost:
            try:
                ct   = bytes.fromhex(value)
                data = self._gost.decrypt(ct)
                return data.get("v", value)
            except Exception as e:
                log.debug("Grist decrypt: %s", e)
        return value

    # ── Публичный API ─────────────────────────────────────────────────────────

    def save(self, key: str, value: Any) -> str:
        """Сохраняет ключ-значение для текущей ноды."""
        if not self._configured:
            return "❌ Grist не настроен. Укажи GRIST_API_KEY и GRIST_DOC_ID."
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)

        enc_val, is_enc = self._enc(value)
        ts = datetime.utcnow().isoformat()

        # Обновляем если запись уже есть
        try:
            rows = self._client.fetch_rows(TABLE_STORE, {
                "node_id": [self._node_id], "key": [key]
            })
            if rows:
                self._client.update_row(TABLE_STORE, rows[0]["_id"], {
                    "value": enc_val, "encrypted": is_enc, "updated_at": ts
                })
                return f"✅ Grist обновлено: {key}"
        except Exception:
            pass

        self._client.add_row(TABLE_STORE, {
            "node_id": self._node_id, "key": key,
            "value": enc_val, "encrypted": is_enc, "updated_at": ts,
        })
        return f"✅ Grist сохранено: {key} {'(ГОСТ)' if is_enc else ''}"

    def get(self, key: str) -> str:
        """Получает значение по ключу для текущей ноды."""
        if not self._configured:
            return "❌ Grist не настроен."
        try:
            rows = self._client.fetch_rows(TABLE_STORE, {
                "node_id": [self._node_id], "key": [key]
            })
            if not rows:
                return f"❌ Grist: ключ '{key}' не найден."
            r = rows[0]
            val = self._dec(r.get("value", ""), bool(r.get("encrypted", False)))
            return f"🗄 Grist [{key}]: {val}"
        except Exception as e:
            return f"❌ Grist get: {e}"

    def list_keys(self, all_nodes: bool = False) -> str:
        """Список всех ключей (текущей или всех нод)."""
        if not self._configured:
            return "❌ Grist не настроен."
        try:
            filt = {} if all_nodes else {"node_id": [self._node_id]}
            rows = self._client.fetch_rows(TABLE_STORE, filt or None)
            if not rows:
                return "🗄 Grist: записей нет."
            lines = [f"🗄 Grist ({len(rows)} записей):"]
            for r in rows:
                enc = "🔐" if r.get("encrypted") else ""
                lines.append(f"  [{r.get('node_id','?')}] {r.get('key','?')}"
                             f"  {enc}  {r.get('updated_at','')[:16]}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Grist list: {e}"

    def sync_node(self, node_id: str = None, hostname: str = None,
                  ip: str = None, port: int = 55771) -> str:
        """Регистрирует / обновляет ноду в Grist (P2P обнаружение)."""
        if not self._configured:
            return "❌ Grist не настроен."
        node_id  = node_id or self._node_id
        hostname = hostname or socket.gethostname()
        ip       = ip or ""
        ts       = datetime.utcnow().isoformat()
        try:
            rows = self._client.fetch_rows(TABLE_NODES, {"node_id": [node_id]})
            fields = {
                "node_id": node_id, "hostname": hostname, "ip": ip,
                "port": port, "version": "2.0", "seen_at": ts,
                "gost": bool(self._gost),
            }
            if rows:
                self._client.update_row(TABLE_NODES, rows[0]["_id"], fields)
            else:
                self._client.add_row(TABLE_NODES, fields)
            return f"✅ Grist P2P: нода {node_id} зарегистрирована"
        except Exception as e:
            return f"❌ Grist sync_node: {e}"

    def get_nodes(self) -> str:
        """Список нод из Grist-реестра."""
        if not self._configured:
            return "❌ Grist не настроен."
        try:
            rows = self._client.fetch_rows(TABLE_NODES)
            if not rows:
                return "🌐 Grist P2P: ноды не зарегистрированы."
            lines = [f"🌐 Grist P2P: {len(rows)} нод(а):"]
            for r in rows:
                gost = "🔐ГОСТ" if r.get("gost") else ""
                lines.append(
                    f"  [{r.get('node_id','?')[:12]}] "
                    f"{r.get('hostname','?')} {r.get('ip','?')}:{r.get('port','?')} "
                    f"{gost}  last:{r.get('seen_at','')[:16]}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Grist get_nodes: {e}"

    def log_event(self, event: str, data: Any = None) -> None:
        """Логирует событие в Grist (fire-and-forget)."""
        if not self._configured:
            return
        try:
            self._client.add_row(TABLE_EVENTS, {
                "node_id": self._node_id,
                "event":   event,
                "data":    json.dumps(data, ensure_ascii=False) if data else "",
                "ts":      datetime.utcnow().isoformat(),
            })
        except Exception as e:
            log.debug("Grist log_event: %s", e)

    def list_tables(self) -> str:
        """Список таблиц Grist-документа."""
        if not self._configured:
            return "❌ Grist не настроен."
        try:
            tables = self._client.list_tables()
            return "📋 Grist таблицы: " + ", ".join(tables)
        except Exception as e:
            return f"❌ Grist list_tables: {e}"

    def status(self) -> str:
        """Статус Grist-хранилища."""
        lines = [
            "🗄 GRIST P2P ХРАНИЛИЩЕ:",
            f"  Настроен:    {'✅' if self._configured else '❌ нет GRIST_API_KEY/GRIST_DOC_ID'}",
            f"  Сервер:      {GRIST_SERVER}",
            f"  Документ:    {GRIST_DOC_ID or '(не задан)'}",
            f"  ГОСТ-шифр:   {'✅ Кузнечик-CTR' if self._gost else '⚠️ выкл'}",
            f"  Node ID:     {self._node_id}",
        ]
        if self._configured:
            try:
                ok = self._client.ping()
                lines.append(f"  API ping:    {'✅ OK' if ok else '❌ недоступен'}")
            except Exception as e:
                lines.append(f"  API ping:    ❌ {e}")
        lines.append("\nПеременные окружения:")
        lines.append("  GRIST_API_KEY    — ключ API")
        lines.append("  GRIST_SERVER_URL — URL сервера (по умолч. https://docs.getgrist.com)")
        lines.append("  GRIST_DOC_ID     — ID документа из URL /doc/<ID>")
        lines.append("  GRIST_ENCRYPT    — on/off ГОСТ-шифрование (по умолч. on)")
        return "\n".join(lines)
