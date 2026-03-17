"""
hardware_guard.py — Квантовый гомеостаз железа
  Мониторинг CPU/RAM/температуры и автоматическая стабилизация системы.
"""
import os
import time
import threading
import psutil

from src.argos_logger import get_logger

log = get_logger("argos.hardware_guard")


class HardwareHomeostasisGuard:
    def __init__(self, core):
        self.core = core
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._last = {
            "cpu": 0.0,
            "ram": 0.0,
            "temp": None,
            "state": "Normal",
            "mitigation": "none",
            "ts": 0.0,
        }

        self.interval_sec = max(2, int(os.getenv("ARGOS_HOMEOSTASIS_INTERVAL", "8") or "8"))
        self.protect_cpu = float(os.getenv("ARGOS_HOMEOSTASIS_PROTECT_CPU", "78") or "78")
        self.unstable_cpu = float(os.getenv("ARGOS_HOMEOSTASIS_UNSTABLE_CPU", "92") or "92")
        self.protect_ram = float(os.getenv("ARGOS_HOMEOSTASIS_PROTECT_RAM", "82") or "82")
        self.unstable_ram = float(os.getenv("ARGOS_HOMEOSTASIS_UNSTABLE_RAM", "94") or "94")
        self.protect_temp = float(os.getenv("ARGOS_HOMEOSTASIS_PROTECT_TEMP", "76") or "76")
        self.unstable_temp = float(os.getenv("ARGOS_HOMEOSTASIS_UNSTABLE_TEMP", "86") or "86")

    def start(self) -> str:
        if self._running:
            return "🛡️ Гомеостаз уже активен."
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Hardware guard: ON")
        return "🛡️ Квантовый гомеостаз активирован."

    def stop(self) -> str:
        self._running = False
        log.info("Hardware guard: OFF")
        return "🛡️ Квантовый гомеостаз отключён."

    def status(self) -> str:
        with self._lock:
            snap = dict(self._last)
        temp_str = "N/A" if snap["temp"] is None else f"{snap['temp']:.1f}°C"
        return (
            "🛡️ КВАНТОВЫЙ ГОМЕОСТАЗ\n"
            f"  Статус: {'🟢 Активен' if self._running else '🔴 Отключён'}\n"
            f"  Состояние: {snap['state']}\n"
            f"  CPU: {snap['cpu']:.1f}% | RAM: {snap['ram']:.1f}% | TEMP: {temp_str}\n"
            f"  Митигация: {snap['mitigation']}"
        )

    def _loop(self):
        while self._running:
            cpu, ram, temp = self._sample()
            state = self._decide_state(cpu, ram, temp)
            mitigation = self._apply_mitigation(state, cpu, ram, temp)
            with self._lock:
                self._last = {
                    "cpu": cpu,
                    "ram": ram,
                    "temp": temp,
                    "state": state,
                    "mitigation": mitigation,
                    "ts": time.time(),
                }
            time.sleep(self.interval_sec)

    def _sample(self) -> tuple[float, float, float | None]:
        cpu = psutil.cpu_percent(interval=0.25)
        ram = psutil.virtual_memory().percent
        temp = None
        try:
            sensors = psutil.sensors_temperatures() or {}
            vals = []
            for entries in sensors.values():
                for entry in entries:
                    val = getattr(entry, "current", None)
                    if isinstance(val, (int, float)):
                        vals.append(float(val))
            if vals:
                temp = max(vals)
        except Exception:
            temp = None
        return float(cpu), float(ram), temp

    def _decide_state(self, cpu: float, ram: float, temp: float | None) -> str:
        temp_val = temp if temp is not None else 0.0
        unstable = (
            cpu >= self.unstable_cpu or
            ram >= self.unstable_ram or
            (temp is not None and temp_val >= self.unstable_temp)
        )
        if unstable:
            return "Unstable"

        protective = (
            cpu >= self.protect_cpu or
            ram >= self.protect_ram or
            (temp is not None and temp_val >= self.protect_temp)
        )
        if protective:
            return "Protective"
        return "Analytic"

    def _apply_mitigation(self, state: str, cpu: float, ram: float, temp: float | None) -> str:
        if state == "Unstable":
            self.core._homeostasis_block_heavy = True
            self.core.auto_collab_enabled = False
            self.core.auto_collab_max_models = 2
            if hasattr(self.core, "context") and self.core.context:
                self.core.context.set_quantum_state("Unstable")
            if hasattr(self.core, "quantum") and self.core.quantum:
                self.core.quantum.set_state("Unstable")
            return "heavy_tasks=blocked, auto_collab=off"

        if state == "Protective":
            self.core._homeostasis_block_heavy = True
            self.core.auto_collab_enabled = False
            self.core.auto_collab_max_models = 2
            if hasattr(self.core, "context") and self.core.context:
                self.core.context.set_quantum_state("Protective")
            if hasattr(self.core, "quantum") and self.core.quantum:
                self.core.quantum.set_state("Protective")
            return "heavy_tasks=throttled, auto_collab=off"

        self.core._homeostasis_block_heavy = False
        if hasattr(self.core, "context") and self.core.context:
            self.core.context.set_quantum_state("Analytic")
        if hasattr(self.core, "quantum") and self.core.quantum:
            self.core.quantum.set_state("Analytic")
        return "none"
