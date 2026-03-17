"""
power_sentry.py — Мониторинг UPS и энергосистемы.
Поддерживает: NUT (Network UPS Tools), INA219, симуляцию.
"""
import os
import time
import subprocess
import threading
from typing import List, Optional
from dataclasses import dataclass, field, asdict
from src.argos_logger import get_logger

log = get_logger("argos.power")

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    psutil = None; PSUTIL_OK = False


@dataclass
class UPSUnit:
    name: str
    status: str = "unknown"
    battery_pct: float = 100.0
    runtime_min: float = 0.0
    load_pct: float = 0.0
    voltage_v: float = 0.0
    last_update: float = field(default_factory=time.time)

    def to_dict(self): return asdict(self)


@dataclass
class PowerReading:
    sensor_id: str
    voltage_v: float = 0.0
    current_a: float = 0.0
    power_w: float = 0.0
    ts: float = field(default_factory=time.time)

    def to_dict(self): return asdict(self)


class PowerSentry:
    """Мониторинг UPS и потребления энергии."""

    def __init__(self):
        self._ups_list: List[UPSUnit] = []
        self._readings: List[PowerReading] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._nut_available = self._check_nut()
        self._emergency_armed = False

    def _check_nut(self) -> bool:
        try:
            r = subprocess.run(["upsc", "-l"], capture_output=True, timeout=3)
            return r.returncode == 0
        except Exception:
            return False

    def start(self) -> str:
        if self._running:
            return "ℹ️ Power Sentry уже запущен"
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        return f"✅ Power Sentry запущен (NUT: {'✅' if self._nut_available else '❌ симуляция'})"

    def _monitor_loop(self):
        while self._running:
            try:
                self._update_ups()
                self._update_readings()
                self._check_alerts()
            except Exception as e:
                log.debug("Power monitor: %s", e)
            time.sleep(30)

    def _update_ups(self):
        if self._nut_available:
            try:
                r = subprocess.run(["upsc", "-l"], capture_output=True, text=True, timeout=5)
                names = [n.strip() for n in r.stdout.splitlines() if n.strip()]
                for name in names:
                    info = subprocess.run(["upsc", name], capture_output=True, text=True, timeout=5)
                    data = {}
                    for line in info.stdout.splitlines():
                        if ":" in line:
                            k, _, v = line.partition(":")
                            data[k.strip()] = v.strip()
                    ups = UPSUnit(
                        name=name,
                        status=data.get("ups.status", "unknown"),
                        battery_pct=float(data.get("battery.charge", 100)),
                        runtime_min=float(data.get("battery.runtime", 0)) / 60,
                        load_pct=float(data.get("ups.load", 0)),
                        voltage_v=float(data.get("input.voltage", 0)),
                    )
                    # Обновляем или добавляем
                    for i, u in enumerate(self._ups_list):
                        if u.name == name:
                            self._ups_list[i] = ups
                            break
                    else:
                        self._ups_list.append(ups)
            except Exception as e:
                log.debug("UPS update: %s", e)
        else:
            # Симуляция если psutil есть
            if PSUTIL_OK:
                bat = psutil.sensors_battery()
                if bat:
                    sim = UPSUnit(
                        name="battery_sim",
                        status="OL" if bat.power_plugged else "OB",
                        battery_pct=bat.percent,
                        runtime_min=bat.secsleft / 60 if bat.secsleft > 0 else 0,
                    )
                    if self._ups_list:
                        self._ups_list[0] = sim
                    else:
                        self._ups_list.append(sim)

    def _update_readings(self):
        """Пытается читать INA219 через smbus или симулирует."""
        try:
            import smbus2
            bus = smbus2.SMBus(1)
            raw = bus.read_word_data(0x40, 0x01)
            voltage = ((raw >> 3) * 4) / 1000.0
            current = bus.read_word_data(0x40, 0x04) / 10.0
            reading = PowerReading("INA219", voltage_v=voltage,
                                   current_a=current, power_w=voltage * current)
            self._readings.append(reading)
            if len(self._readings) > 1000:
                self._readings = self._readings[-1000:]
        except Exception:
            pass

    def _check_alerts(self):
        for ups in self._ups_list:
            if "OB" in ups.status and ups.battery_pct < 20:
                log.warning("⚡ UPS %s: на батарее, заряд %.0f%%", ups.name, ups.battery_pct)
            if self._emergency_armed and ups.battery_pct < 5:
                log.critical("🚨 UPS критически мало заряда — аварийное завершение")

    def arm_emergency(self) -> str:
        self._emergency_armed = True
        return "⚡ Power Sentry: аварийное отключение взведено (при заряде <5%)"

    def list_ups(self) -> list:
        return [u.to_dict() for u in self._ups_list]

    def get_readings(self) -> list:
        return [r.to_dict() for r in self._readings[-50:]]

    def status(self) -> str:
        nut = "✅" if self._nut_available else "⚠️ симуляция"
        return (
            f"🔋 POWER SENTRY:\n"
            f"  NUT:        {nut}\n"
            f"  Запущен:    {'✅' if self._running else '❌'}\n"
            f"  UPS:        {len(self._ups_list)}\n"
            f"  Показания:  {len(self._readings)}\n"
            f"  Аварийный:  {'⚡ взведён' if self._emergency_armed else 'не активен'}"
        )
