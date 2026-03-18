"""quantum/logic.py — квантовые состояния Аргоса"""
import time

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


class QuantumEngine:
    def __init__(self):
        self.current = "Analytic"
        self._ts = time.time()

    def generate_state(self) -> dict:
        self._auto_switch()
        return {"name": self.current, "vector": list(STATES[self.current].values())}

    def _auto_switch(self):
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


ArgosQuantum = QuantumEngine
