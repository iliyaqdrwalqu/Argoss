\
"""
tasmota_updater.py — Автоматическое скачивание прошивок Tasmota с OTA-сервера.
Команды: обнови тасмота | обнови tasmota | скачай прошивки
"""
import logging
import os
import requests

log = logging.getLogger("argos.skills.tasmota_updater")

TRIGGERS = ["обнови тасмота", "обнови tasmota", "tasmota update",
            "скачай прошивки", "обнови прошивки"]


class TasmotaUpdater:
    def __init__(self):
        self.base_url = "http://ota.tasmota.com/tasmota/release/"
        self.targets = {
            "tasmota.bin":         "tasmota_relay.bin",
            "tasmota-sensors.bin": "tasmota_sensor.bin",
            "tasmota-ru.bin":      "tasmota_ru_relay.bin",
        }
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.firmware_dir = os.path.abspath(
            os.path.join(current_dir, "..", "..", "assets", "firmware")
        )

    def _ensure_dir(self):
        os.makedirs(self.firmware_dir, exist_ok=True)

    def handle(self, text: str = "", core=None) -> str | None:
        t = text.lower()
        if not any(tr in t for tr in TRIGGERS):
            return None
        return self.execute(text, core)

    def execute(self, text: str = "", core=None) -> str:
        self._ensure_dir()
        results = []
        for tasmota_file, argos_name in self.targets.items():
            url = self.base_url + tasmota_file
            save_path = os.path.join(self.firmware_dir, argos_name)
            try:
                log.info("Скачивание %s...", tasmota_file)
                r = requests.get(url, stream=True, timeout=15)
                if r.status_code == 200:
                    with open(save_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    size = os.path.getsize(save_path)
                    results.append(f"  ✅ {argos_name} ({size//1024} KB)")
                else:
                    results.append(f"  ❌ {tasmota_file}: HTTP {r.status_code}")
            except Exception as e:
                log.error("Ошибка скачивания %s: %s", tasmota_file, e)
                results.append(f"  ❌ {tasmota_file}: {e}")

        return (
            f"🔄 Tasmota обновление → {self.firmware_dir}\\n"
            + "\\n".join(results)
            + "\\n\\nТеперь доступна: умная прошивка /dev/ttyUSB0 tasmota_relay"
        )

    def list_local(self) -> str:
        self._ensure_dir()
        bins = [f for f in os.listdir(self.firmware_dir) if f.endswith(".bin")]
        if not bins:
            return f"📁 {self.firmware_dir}: прошивок нет. Запусти: обнови тасмота"
        lines = [f"📁 Tasmota прошивки ({self.firmware_dir}):"]
        for b in sorted(bins):
            sz = os.path.getsize(os.path.join(self.firmware_dir, b))
            lines.append(f"  • {b} ({sz//1024} KB)")
        return "\\n".join(lines)


def setup():
    return TasmotaUpdater()
