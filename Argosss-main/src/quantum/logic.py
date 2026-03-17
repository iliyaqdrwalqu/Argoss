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

        self._forced_until: float = 0.0
        self.evidence: dict = {"user_active": True}
=======
        # Forced-state TTL support
        self._forced_state: Optional[str] = None
        self._forced_until: float = 0.0
        # External telemetry (cpu/ram/temp) override
        self._ext_cpu: Optional[float] = None
        self._ext_ram: Optional[float] = None
        self._ext_temp: Optional[float] = None
        self._ext_until: float = 0.0
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


    def _auto_switch(self):
        if time.time() < self._forced_until:
            return
        if not _PSUTIL:
            return
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            if cpu > 85 or ram > 90:
                self.current = "Protective"
            elif cpu > 70:
                self.current = "Unstable"
        except Exception:
            pass

=======

    def set_state(self, name: str) -> str:
        if name in STATES:
            self.current = name
            return f"⚛️ Квантовое состояние: {name}"
        return f"❌ Неизвестное состояние: {name}"


    def force_state(self, name: str, ttl_seconds: int = 60) -> str:
        """Принудительно установить состояние на заданное время (игнорирует auto_switch)."""
        if name not in STATES:
            return f"❌ Неизвестное состояние: {name}"
        self.current = name
        self._forced_until = time.time() + ttl_seconds
        return f"⚛️ Состояние зафиксировано: {name} на {ttl_seconds}с"

    def set_external_telemetry(self, cpu: float = None, ram: float = None,
                                temp: float = None, ttl_seconds: int = 60) -> None:
        """Обновить состояние на основе внешней телеметрии (CPU%, RAM%, температура)."""
        if cpu is not None and cpu > 85:
            self.force_state("Protective", ttl_seconds)
        elif ram is not None and ram > 90:
            self.force_state("Protective", ttl_seconds)
        elif cpu is not None and cpu > 70:
            self.force_state("Unstable", ttl_seconds)

    def _is_user_active(self) -> bool:
        """Определить активность пользователя (переопределяется в тестах)."""
        return True

    def _update_evidence(self) -> None:
        """Обновить словарь evidence текущими показателями системы."""
        self.evidence["user_active"] = self._is_user_active()

    def _effective_metric(self, cpu: float = 0.0, ram: float = 0.0) -> float:
        """Агрегированная метрика нагрузки [0..1] для детектора активности."""
        return max(cpu, ram) / 100.0
=======
    def force_state(self, name: str, ttl_seconds: float = 60) -> str:
        """Pin the engine to *name* for *ttl_seconds* seconds, ignoring auto-switch."""
        if name not in STATES:
            return f"❌ Неизвестное состояние: {name}"
        self._forced_state = name
        self._forced_until = time.time() + ttl_seconds
        self.current = name
        return f"⚛️ Состояние зафиксировано: {name} (TTL {ttl_seconds}s)"

    def set_external_telemetry(
        self,
        cpu: Optional[float] = None,
        ram: Optional[float] = None,
        temp: Optional[float] = None,
        ttl_seconds: float = 60,
    ) -> None:
        """Feed external telemetry (e.g. from homeostasis) that overrides psutil readings."""
        self._ext_cpu = cpu
        self._ext_ram = ram
        self._ext_temp = temp
        self._ext_until = time.time() + ttl_seconds

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
        now = time.time()
        # Respect forced state while TTL is active
        if self._forced_state and now < self._forced_until:
            self.current = self._forced_state
            return
        self._forced_state = None

        cpu, ram = self._effective_metric()
        if cpu > _CPU_PROTECTIVE or ram > _RAM_PROTECTIVE:
            self.current = "Protective"
        elif cpu > _CPU_UNSTABLE:
            self.current = "Unstable"

    def _effective_metric(self) -> tuple[float, float]:
        """Return (cpu%, ram%) from external telemetry if active, else psutil."""
        now = time.time()
        if self._ext_cpu is not None and now < self._ext_until:
            return self._ext_cpu, (self._ext_ram or 0.0)
        if not _PSUTIL:
            return 0.0, 0.0
        try:
            return (
                psutil.cpu_percent(interval=0.1),
                psutil.virtual_memory().percent,
            )
        except Exception:
            return 0.0, 0.0

    def _is_user_active(self) -> bool:
        """Heuristic: consider user active when CPU is above idle threshold."""
        cpu, _ = self._effective_metric()
        return cpu > _CPU_IDLE

    def _update_evidence(self) -> None:
        """Refresh the `evidence` dict used by external observers (e.g. homeostasis)."""
        try:
            self.evidence["cpu"], self.evidence["ram"] = self._effective_metric()
        except (TypeError, ValueError):
            pass
        self.evidence["user_active"] = self._is_user_active()


ArgosQuantum = QuantumEngine
