"""
sensor_bridge.py -- System sensor bridge for ARGOS.
CPU / RAM / disk / battery / temperature / network.
"""
import platform, socket, time
from collections import deque
from typing import Any, Dict

import psutil

from src.argos_logger import get_logger
log = get_logger("argos.sensor")


class ArgosSensorBridge:
    MAX_HISTORY = 120

    def __init__(self):
        self.os_type = platform.system()
        self._history = deque(maxlen=self.MAX_HISTORY)
        self._cache: Dict[str, Any] = {}
        self._cache_ts = 0.0

    def get_metrics(self) -> Dict[str, Any]:
        now = time.time()
        if self._cache and (now - self._cache_ts) < 1.0:
            return self._cache
        m: Dict[str, Any] = {
            "ts":            now,
            "cpu_percent":   psutil.cpu_percent(interval=0.1),
            "ram_percent":   psutil.virtual_memory().percent,
            "ram_used_mb":   psutil.virtual_memory().used // (1024*1024),
            "ram_total_mb":  psutil.virtual_memory().total // (1024*1024),
            "disk_percent":  self._disk_percent(),
            "disk_free_gb":  self._disk_free_gb(),
            "cpu_freq_mhz":  self._cpu_freq(),
            "cpu_cores":     psutil.cpu_count(logical=True),
            "temperature":   self._get_temperature(),
            "battery":       self._check_battery(),
            "network":       self._ping_status(),
            "load_avg":      self._load_avg(),
            "uptime_sec":    int(now - psutil.boot_time()),
        }
        self._cache = m
        self._cache_ts = now
        self._history.append({"ts": now, "cpu": m["cpu_percent"], "ram": m["ram_percent"]})
        return m

    def get_vital_signs(self) -> Dict[str, Any]:
        m = self.get_metrics()
        return {
            "battery": m["battery"],
            "thermal": m["temperature"],
            "network": m["network"],
            "storage": {"free_gb": f"{m['disk_free_gb']} GB", "load": f"{m['disk_percent']}%"},
        }

    def get_full_report(self) -> str:
        m = self.get_metrics()
        bat = m["battery"]
        bat_s = (f"{bat['percent']} ({bat['plugged']})" if isinstance(bat, dict) else str(bat))
        net = m["network"]
        net_s = (f"{net['ping']} ({net['status']})" if isinstance(net, dict) else str(net))
        uh = m["uptime_sec"] // 3600
        um = (m["uptime_sec"] % 3600) // 60
        return (
            f"HEALTH REPORT ({self.os_type})\n"
            f"  CPU:   {m['cpu_percent']:.1f}%  ({m['cpu_cores']} cores @ {m['cpu_freq_mhz']} MHz)\n"
            f"  RAM:   {m['ram_percent']:.1f}%  ({m['ram_used_mb']} / {m['ram_total_mb']} MB)\n"
            f"  Disk:  {m['disk_percent']:.1f}%  (free {m['disk_free_gb']} GB)\n"
            f"  Temp:  {m['temperature']}\n"
            f"  Net:   {net_s}\n"
            f"  Bat:   {bat_s}\n"
            f"  Up:    {uh}h {um}m"
        )

    def _check_battery(self):
        b = psutil.sensors_battery()
        if b:
            return {"percent": f"{b.percent:.0f}%",
                    "plugged": "Connected" if b.power_plugged else "Discharging",
                    "time_left": f"{b.secsleft//60} min" if b.secsleft not in (-1,-2) else "N/A"}
        return "N/A (Stationary)"

    def _get_temperature(self) -> str:
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    all_t = [s.current for v in temps.values() for s in v]
                    if all_t:
                        return f"{max(all_t):.1f}degC"
        except Exception:
            pass
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return f"{int(f.read().strip())/1000:.1f}degC"
        except Exception:
            pass
        return "N/A"

    def _ping_status(self) -> Dict[str, str]:
        try:
            t0 = time.time()
            with socket.create_connection(("8.8.8.8", 53), timeout=2):
                pass
            ms = int((time.time()-t0)*1000)
            return {"ping": f"{ms}ms", "status": "Stable" if ms < 100 else "Degraded"}
        except Exception:
            return {"ping": "inf", "status": "Offline"}

    def _disk_percent(self) -> float:
        try:
            return psutil.disk_usage("/").percent
        except Exception:
            return 0.0

    def _disk_free_gb(self) -> int:
        try:
            return psutil.disk_usage("/").free // (1024**3)
        except Exception:
            return 0

    def _cpu_freq(self) -> int:
        try:
            f = psutil.cpu_freq()
            return int(f.current) if f else 0
        except Exception:
            return 0

    def _load_avg(self) -> str:
        try:
            la = psutil.getloadavg()
            return f"{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}"
        except Exception:
            return "N/A"

    def history_avg(self, window: int = 60) -> Dict[str, float]:
        now = time.time()
        recent = [h for h in self._history if (now - h["ts"]) <= window]
        if not recent:
            return {"cpu": 0.0, "ram": 0.0}
        return {
            "cpu": round(sum(h["cpu"] for h in recent) / len(recent), 2),
            "ram": round(sum(h["ram"] for h in recent) / len(recent), 2),
        }


SensorBridge = ArgosSensorBridge

# Aliases
SensorBridge = ArgosSensorBridge
