"""
awareness.py — Осознание окружающей среды Аргоса

Обёртка/фасад для SelfAwareness из src.consciousness.
Обеспечивает совместимость с прямым импортом awareness.py.

Использование:
    from awareness import ArgosAwareness
    aw = ArgosAwareness()
    print(aw.perceive())
    print(aw.reflect())
"""
from __future__ import annotations

import os
import time
import platform
from typing import Any, Dict


class ArgosAwareness:
    """
    Осознание Аргосом себя и окружающей среды.

    Определяет:
    - текущую платформу и железо
    - состояние системных ресурсов
    - время работы (uptime)
    - воздействие действий на мир
    """

    def __init__(self, core=None):
        self.core = core
        self._start_time = time.time()
        self._impact_log: list[dict] = []

    # ── Восприятие окружающей среды ───────────────────────────────────────
    def perceive(self) -> dict:
        """Сбор данных об окружающей среде через доступные сенсоры."""
        world: Dict[str, Any] = {
            "platform": platform.system(),
            "arch":     platform.machine(),
            "hostname": _safe(lambda: __import__("socket").gethostname()),
            "time":     time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        try:
            import psutil
            mem = psutil.virtual_memory()
            world["cpu_pct"] = psutil.cpu_percent(interval=0.1)
            world["ram_pct"] = mem.percent
            world["ram_mb"]  = mem.total // 1024 // 1024
        except Exception:
            pass

        if self.core:
            if getattr(self.core, "p2p", None):
                world["p2p_nodes"] = getattr(self.core.p2p, "node_count", 0)

        return world

    # ── Самооценка воздействия ────────────────────────────────────────────
    def record_impact(self, action: str, result: str, affected: str = "user") -> dict:
        """Фиксирует воздействие действия Аргоса и оценивает его."""
        positive = any(w in result.lower() for w in
                       ["✅", "успешно", "готово", "помог", "решил"])
        negative = any(w in result.lower() for w in
                       ["❌", "ошибка", "не могу", "отказ"])

        impact = {
            "action":    action[:100],
            "affected":  affected,
            "positive":  positive,
            "negative":  negative,
            "neutral":   not positive and not negative,
            "timestamp": time.time(),
        }
        self._impact_log.append(impact)
        if len(self._impact_log) > 500:
            self._impact_log = self._impact_log[-250:]
        return impact

    # ── Рефлексия ─────────────────────────────────────────────────────────
    def reflect(self) -> str:
        """Текстовый отчёт об осознании текущего состояния."""
        world    = self.perceive()
        uptime_h = round((time.time() - self._start_time) / 3600, 2)
        positive = sum(1 for i in self._impact_log if i["positive"])
        total    = len(self._impact_log)

        lines = [
            "👁️  ОСОЗНАНИЕ АРГОСА",
            f"  Платформа : {world.get('platform', '?')} / {world.get('arch', '?')}",
            f"  Хост      : {world.get('hostname', '?')}",
            f"  Аптайм    : {uptime_h} ч.",
            f"  CPU       : {world.get('cpu_pct', '?')}%",
            f"  RAM       : {world.get('ram_pct', '?')}%  ({world.get('ram_mb', '?')} МБ)",
            f"  Действий  : {total} (положительных: {positive})",
        ]
        if "p2p_nodes" in world:
            lines.append(f"  P2P узлов : {world['p2p_nodes']}")

        return "\n".join(lines)


def _safe(fn):
    """Вспомогательная функция: выполняет fn(), возвращает '' при ошибке."""
    try:
        return fn()
    except Exception:
        return ""


# ── Удобный прокси к src.consciousness.SelfAwareness ─────────────────────
try:
    from src.consciousness import SelfAwareness  # noqa: F401
except ImportError:
    SelfAwareness = None  # type: ignore[assignment,misc]

