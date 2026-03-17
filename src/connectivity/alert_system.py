"""
alert_system.py — Система автоматических алертов
  Следит за CPU/RAM/диском/температурой.
  При превышении порогов — уведомление в Telegram + консоль.
"""
import threading
import time
import os
import requests
import psutil
from src.argos_logger import get_logger

log = get_logger("argos.alerts")

THRESHOLDS = {
    "cpu":    90.0,   # %
    "ram":    85.0,   # %
    "disk":   90.0,   # %
    "temp":   85.0,   # °C
}

class AlertSystem:
    def __init__(self, on_alert=None):
        """
        on_alert: callable(msg) — вызывается при срабатывании алерта.
        Если None — использует Telegram Bot API напрямую.
        """
        self._on_alert  = on_alert
        self._running   = False
        self._cooldown  = {}   # name → last_alert_time (избегаем спама)
        self._cooldown_sec = 300  # 5 минут между одинаковыми алертами
        self._tg_token  = os.getenv("TELEGRAM_BOT_TOKEN")
        self._tg_chatid = os.getenv("USER_ID")

    def start(self, interval_sec: int = 30) -> str:
        self._running = True
        threading.Thread(target=self._loop, args=(interval_sec,), daemon=True).start()
        log.info("AlertSystem запущен. Интервал: %ds", interval_sec)
        return f"🔔 Система алертов активна. Проверка каждые {interval_sec}с."

    def stop(self):
        self._running = False
        log.info("AlertSystem остановлен.")

    def _loop(self, interval: int):
        while self._running:
            self.check_all()
            time.sleep(interval)

    def check_all(self) -> list[str]:
        alerts = []

        # CPU
        cpu = psutil.cpu_percent(interval=1)
        if cpu >= THRESHOLDS["cpu"]:
            alerts.append(self._fire("cpu", f"🔥 CPU перегружен: {cpu:.1f}% (порог {THRESHOLDS['cpu']}%)"))

        # RAM
        ram = psutil.virtual_memory().percent
        if ram >= THRESHOLDS["ram"]:
            alerts.append(self._fire("ram", f"💾 RAM критически заполнена: {ram:.1f}% (порог {THRESHOLDS['ram']}%)"))

        # Диск
        try:
            disk = psutil.disk_usage('/').percent
            if disk >= THRESHOLDS["disk"]:
                free_gb = psutil.disk_usage('/').free // (2**30)
                alerts.append(self._fire("disk", f"💿 Диск почти заполнен: {disk:.1f}% (свободно {free_gb}GB)"))
        except Exception:
            pass

        # Температура
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    max_t = max(s.current for sensors in temps.values() for s in sensors)
                    if max_t >= THRESHOLDS["temp"]:
                        alerts.append(self._fire("temp", f"🌡️ Перегрев: {max_t:.1f}°C (порог {THRESHOLDS['temp']}°C)"))
        except Exception:
            pass

        # Процессы-зомби
        try:
            zombies = [p for p in psutil.process_iter(['status']) if p.info['status'] == 'zombie']
            if len(zombies) > 5:
                alerts.append(self._fire("zombie", f"👻 Зомби-процессов: {len(zombies)}"))
        except Exception:
            pass

        return [a for a in alerts if a]

    def _fire(self, name: str, msg: str) -> str | None:
        """Срабатывает алерт с учётом кулдауна."""
        now = time.time()
        last = self._cooldown.get(name, 0)
        if now - last < self._cooldown_sec:
            return None  # кулдаун не истёк

        self._cooldown[name] = now
        full_msg = f"⚠️ ARGOS ALERT\n{msg}"
        log.warning("ALERT: %s", msg)

        # Callback (например, GUI или Telegram bot)
        if self._on_alert:
            try: self._on_alert(full_msg)
            except Exception as e: log.error("Alert callback error: %s", e)
        else:
            self._send_telegram(full_msg)

        return msg

    def _send_telegram(self, msg: str):
        if not self._tg_token or not self._tg_chatid:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self._tg_token}/sendMessage",
                json={"chat_id": self._tg_chatid, "text": msg},
                timeout=5,
            )
        except Exception as e:
            log.error("Telegram alert send error: %s", e)

    def set_threshold(self, metric: str, value: float) -> str:
        if metric not in THRESHOLDS:
            return f"❌ Неизвестная метрика. Доступные: {list(THRESHOLDS.keys())}"
        THRESHOLDS[metric] = value
        return f"✅ Порог {metric} установлен: {value}"

    def status(self) -> str:
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory().percent
        try: disk = psutil.disk_usage('/').percent
        except: disk = 0
        lines = [
            "🔔 СИСТЕМА АЛЕРТОВ:",
            f"  CPU:  {cpu:.1f}% {'🔥' if cpu >= THRESHOLDS['cpu'] else '✅'} (порог {THRESHOLDS['cpu']}%)",
            f"  RAM:  {ram:.1f}% {'💾' if ram >= THRESHOLDS['ram'] else '✅'} (порог {THRESHOLDS['ram']}%)",
            f"  Диск: {disk:.1f}% {'💿' if disk >= THRESHOLDS['disk'] else '✅'} (порог {THRESHOLDS['disk']}%)",
            f"  Мониторинг: {'🟢 Активен' if self._running else '🔴 Остановлен'}",
        ]
        return "\n".join(lines)
