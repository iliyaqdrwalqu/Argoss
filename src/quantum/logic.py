"""quantum/logic.py — квантовые состояния Аргоса"""
import time
from typing import Optional

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

STATES = {
    "Analytic":   {"creativity": 0.2, "window": 6,  "allow_root": True},
    "Creative":   {"creativity": 0.9, "window": 15, "allow_root": False},
    "Protective": {"creativity": 0.1, "window": 8,  "allow_root": False},
    "Unstable":   {"creativity": 0.5, "window": 4,  "allow_root": False},
    "All-Seeing": {"creativity": 0.7, "window": 20, "allow_root": True},
    "System":     {"creativity": 0.0, "window": 5,  "allow_root": True},
}

# Thresholds used by evidence-based state selection
_CPU_PROTECTIVE  = 85.0
_RAM_PROTECTIVE  = 90.0
_CPU_UNSTABLE    = 70.0
_CPU_IDLE        = 5.0    # below this threshold, user is considered inactive


class QuantumEngine:
    def __init__(self):
        self.current = "Analytic"
        self._ts = time.time()
        # Evidence dict used by homeostasis / activity detector integration
        self.evidence: dict = {
            "user_active": False,
            "cpu": 0.0,
            "ram": 0.0,
        }

    # ── Public API ──────────────────────────────────────────────────

    def generate_state(self) -> dict:
        self._auto_switch()
        return {"name": self.current, "vector": list(STATES[self.current].values())}

    def set_state(self, name: str) -> str:
        if name in STATES:
            self.current = name
            return f"⚛️ Квантовое состояние: {name}"
        return f"❌ Неизвестное состояние: {name}"

    def status(self) -> str:
        s = STATES[self.current]
        return (
            f"⚛️ Состояние: {self.current}\n"
            f"  Творчество: {s['creativity']}\n"
            f"  Окно памяти: {s['window']}\n"
            f"  Root-команды: {s['allow_root']}"
        )

    # ── Internal helpers ────────────────────────────────────────────

    def _auto_switch(self) -> None:
        if not _PSUTIL:
            return
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            if cpu > _CPU_PROTECTIVE or ram > _RAM_PROTECTIVE:
                self.current = "Protective"
            elif cpu > _CPU_UNSTABLE:
                self.current = "Unstable"
        except Exception:
            pass

    def _effective_metric(self, cpu: float = 0.0, ram: float = 0.0) -> float:
        """Агрегированная метрика нагрузки [0..1] для детектора активности."""
        return max(cpu, ram) / 100.0

    def _is_user_active(self) -> bool:
        """Определить активность пользователя (переопределяется в тестах)."""
        return True

    def _update_evidence(self) -> None:
        """Обновить словарь evidence текущими показателями системы."""
        self.evidence["user_active"] = self._is_user_active()


ArgosQuantum = QuantumEngine
