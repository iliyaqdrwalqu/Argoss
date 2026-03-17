"""
biosphere_dag.py — DAG-контроллер биосферы

Directed Acyclic Graph (конвейер):
  SensorReaderNode → ClimateAnalyzerNode → ActuatorNode

Поддерживает автоматический цикл через threading.
"""

import logging
import threading
import time

from src.modules.biosphere_tools import ActuatorNode, ClimateAnalyzerNode, SensorReaderNode

log = logging.getLogger("argos.biosphere.dag")


class BiosphereDAGController:
    """
    DAG-контроллер биосферы.

    Принимает sys_id системы умного дома (home/greenhouse/aquarium…),
    прогоняет данные через пайплайн нод и исполняет актуаторы.
    """

    def __init__(self, core):
        self.core = core
        self.default_profile = {
            "temp_min": 22.0,
            "temp_max": 26.0,
            "hum_min": 60.0,
        }
        self.last_result = ""
        self.last_sys_id = ""
        self._running = False
        self._interval = 30.0
        self._thread = None
        self._auto_sys_id = ""

        # Пайплайн нод
        self.pipeline = [
            SensorReaderNode(),
            ClimateAnalyzerNode(),
            ActuatorNode(),
        ]

    # ── Основной цикл ────────────────────────────────────

    def run_cycle(self, sys_id: str, profile: dict) -> str:
        """Прогоняет один полный цикл управления биосферой."""
        log.info("🔄 DAG: старт цикла для '%s'", sys_id)

        state = {
            "sys_id": sys_id,
            "profile": profile,
        }

        for node in self.pipeline:
            state = node.execute(state, self.core)
            if "error" in state:
                log.error("❌ DAG остановлен: %s", state["error"])
                self.last_result = state["error"]
                self.last_sys_id = sys_id
                return state["error"]

        actions = state.get("executed", [])
        self.last_sys_id = sys_id

        if not actions:
            self.last_result = (
                f"🌿 Биосфера '{sys_id}' в идеальном состоянии. Действий не требуется."
            )
        else:
            self.last_result = (
                f"⚙️ Биосфера '{sys_id}' скорректирована: {', '.join(actions)}"
            )
        return self.last_result

    # ── Автоцикл ─────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                if self._auto_sys_id:
                    self.run_cycle(self._auto_sys_id, dict(self.default_profile))
            except Exception as e:
                log.error("Biosphere loop error: %s", e)
            time.sleep(self._interval)

    def start(self, interval_sec: float = 30.0, sys_id: str = "") -> str:
        """Запустить автоматический цикл мониторинга."""
        self._interval = max(2.0, float(interval_sec or 30.0))
        if sys_id:
            self._auto_sys_id = sys_id
        if self._running:
            return f"🌿 BiosphereDAG: уже запущен (каждые {self._interval}с)."
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="biosphere-dag"
        )
        self._thread.start()
        return f"🌿 BiosphereDAG: автоцикл запущен (каждые {self._interval}с)."

    def stop(self) -> str:
        """Остановить автоцикл."""
        if not self._running:
            return "🌿 BiosphereDAG: не запущен."
        self._running = False
        return "🌿 BiosphereDAG: остановлен."

    # ── API ──────────────────────────────────────────────

    def set_target(self, key: str, value: float) -> str:
        """Обновить целевое значение профиля."""
        self.default_profile[key] = float(value)
        return f"🌿 Целевой профиль: {key}={value}"

    def status(self) -> str:
        lines = ["🌿 BIOSPHERE DAG:"]
        lines.append(f"  Автоцикл: {'ON' if self._running else 'OFF'}")
        lines.append(f"  Интервал: {self._interval}с")
        lines.append(f"  Последняя система: {self.last_sys_id or '—'}")
        lines.append(f"  Профиль: {self.default_profile}")
        if self.last_result:
            lines.append(f"  Результат: {self.last_result}")
        return "\n".join(lines)

    def get_last_result(self) -> str:
        return self.last_result or "Циклов ещё не было."


# Backward-compatibility alias для старых импортов
class BiosphereDAG(BiosphereDAGController):
    """Alias для совместимости с ранними версиями кода."""

    def __init__(self, environment: str = "generic", core=None, tools=None, targets=None):
        super().__init__(core=core)
        if isinstance(targets, dict):
            self.default_profile.update(targets)


# README alias
BiosphereDAGController = BiosphereDAGController
