"""
emergency_purge.py — Экстренное уничтожение данных Argos.
Уровни: logs → cache → data → config → full.
Требует двухшаговое подтверждение (запрос + код).
"""
import os
import shutil
import secrets
import time
import json
from pathlib import Path
from typing import Optional
from src.argos_logger import get_logger

log = get_logger("argos.purge")

PURGE_LEVELS = {
    "logs":   ["logs/"],
    "cache":  ["logs/", "__pycache__/", ".pytest_cache/", "data/cache/"],
    "data":   ["logs/", "data/", "config/node_id", "config/node_birth"],
    "config": ["logs/", "data/", "config/"],
    "full":   ["logs/", "data/", "config/", "builds/", "src/skills/__pycache__/"],
}

HISTORY_FILE = "data/purge_history.json"


class EmergencyPurge:
    def __init__(self):
        self._pending_code: Optional[str] = None
        self._pending_level: Optional[str] = None
        self._pending_ts: float = 0
        self._history: list = self._load_history()
        os.makedirs("data", exist_ok=True)

    def _load_history(self) -> list:
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_history(self) -> None:
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump(self._history[-50:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def request_purge(self, level: str = "logs") -> str:
        """Шаг 1: запрос на очистку. Возвращает код подтверждения."""
        if level not in PURGE_LEVELS:
            avail = ", ".join(PURGE_LEVELS.keys())
            return f"❌ Неверный уровень. Доступные: {avail}"
        self._pending_code = secrets.token_hex(4).upper()
        self._pending_level = level
        self._pending_ts = time.time()
        log.warning("Purge REQUESTED level=%s code=%s", level, self._pending_code)
        return (
            f"⚠️ ЗАПРОС НА ОЧИСТКУ уровень [{level.upper()}]\n"
            f"  Будут удалены: {', '.join(PURGE_LEVELS[level])}\n"
            f"  Код подтверждения: {self._pending_code}\n"
            f"  Введи: purge подтверди {self._pending_code}\n"
            f"  (действует 60 сек)"
        )

    def confirm_purge(self, code: str) -> str:
        """Шаг 2: подтверждение кодом."""
        if not self._pending_code:
            return "❌ Нет активного запроса на очистку"
        if time.time() - self._pending_ts > 60:
            self._pending_code = None
            return "❌ Код истёк. Повтори запрос."
        if code.upper().strip() != self._pending_code:
            return f"❌ Неверный код. Ожидается: {self._pending_code}"

        level = self._pending_level
        targets = PURGE_LEVELS.get(level, [])
        self._pending_code = None
        removed = []
        errors = []

        for target in targets:
            p = Path(target)
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                    p.mkdir(parents=True, exist_ok=True)
                    removed.append(str(p))
                elif p.is_file():
                    p.unlink()
                    removed.append(str(p))
            except Exception as e:
                errors.append(f"{p}: {e}")

        record = {
            "ts": time.time(),
            "level": level,
            "removed": removed,
            "errors": errors,
        }
        self._history.append(record)
        self._save_history()
        log.warning("Purge EXECUTED level=%s removed=%d errors=%d", level, len(removed), len(errors))

        result = f"🗑️ ОЧИСТКА [{level.upper()}] выполнена:\n"
        result += f"  Удалено: {len(removed)} объектов\n"
        if errors:
            result += f"  Ошибки: {len(errors)}\n"
        return result

    def cancel_purge(self) -> str:
        if not self._pending_code:
            return "ℹ️ Нет активного запроса на очистку"
        self._pending_code = None
        self._pending_level = None
        return "✅ Запрос на очистку отменён"

    def history(self) -> str:
        if not self._history:
            return "📋 История очисток: пусто"
        lines = ["📋 ИСТОРИЯ ОЧИСТОК:"]
        for r in self._history[-10:]:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("ts", 0)))
            lines.append(f"  [{ts}] {r.get('level','?').upper()} — {len(r.get('removed',[]))} объектов")
        return "\n".join(lines)

    def status(self) -> str:
        pending = f"⏳ ожидает подтверждения [{self._pending_level}]" if self._pending_code else "idle"
        return (
            f"🗑️ EMERGENCY PURGE:\n"
            f"  Статус:   {pending}\n"
            f"  Уровни:   {', '.join(PURGE_LEVELS.keys())}\n"
            f"  История:  {len(self._history)} записей"
        )
