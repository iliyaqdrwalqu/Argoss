"""
firmware_examples.py — ARGOS Firmware Examples Loader.

Скачивает готовые примеры прошивок и шаблонов из популярных открытых
репозиториев: Tasmota, WLED, ESPHome, Arduino, Micropython.

Команды ядра:
  примеры прошивок                     — список доступных каталогов
  примеры tasmota                      — скачать примеры Tasmota
  примеры wled                         — скачать примеры WLED
  примеры esphome                      — скачать примеры ESPHome
  примеры arduino [тема]               — скачать пример Arduino
  примеры micropython [тема]           — скачать пример MicroPython
  примеры список                       — список скачанных примеров
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

try:
    import requests as _req
    REQUESTS_OK = True
except ImportError:
    _req = None
    REQUESTS_OK = False

log = logging.getLogger("argos.firmware_examples")

FIRMWARE_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "firmware"
))
EXAMPLES_DIR = os.path.join(FIRMWARE_DIR, "examples")

# ─────────────────────────────────────────────────────────────────────────────
# Каталог источников
# ─────────────────────────────────────────────────────────────────────────────

SOURCES: Dict[str, dict] = {
    # ── Tasmota ──────────────────────────────────────────────────────────────
    "tasmota": {
        "description": "Tasmota — прошивка для IoT на ESP32/ESP8266",
        "examples": [
            {
                "name": "tasmota_minimal.bin",
                "url": "http://ota.tasmota.com/tasmota/release/tasmota-minimal.bin",
                "desc": "Tasmota Minimal (esp8266/esp32, минимальный образ)",
            },
            {
                "name": "tasmota.bin",
                "url": "http://ota.tasmota.com/tasmota/release/tasmota.bin",
                "desc": "Tasmota Standard",
            },
            {
                "name": "tasmota-sensors.bin",
                "url": "http://ota.tasmota.com/tasmota/release/tasmota-sensors.bin",
                "desc": "Tasmota Sensors (DHT, DS18B20, BMP, SHT...)",
            },
            {
                "name": "tasmota-display.bin",
                "url": "http://ota.tasmota.com/tasmota/release/tasmota-display.bin",
                "desc": "Tasmota Display (OLED/TFT поддержка)",
            },
            {
                "name": "tasmota32.bin",
                "url": "http://ota.tasmota.com/tasmota32/release/tasmota32.bin",
                "desc": "Tasmota32 (ESP32 стандарт)",
            },
            {
                "name": "tasmota32-sensors.bin",
                "url": "http://ota.tasmota.com/tasmota32/release/tasmota32-sensors.bin",
                "desc": "Tasmota32 Sensors (ESP32)",
            },
            # Tasmota шаблоны конфигурации (JSON, не bin)
            {
                "name": "tasmota_template_sonoff.json",
                "url": ("https://raw.githubusercontent.com/arendst/Tasmota/development/"
                        "tasmota/templates/sonoff_basic.json"),
                "desc": "Шаблон Tasmota для Sonoff Basic",
                "ext": ".json",
            },
        ],
    },

    # ── WLED ─────────────────────────────────────────────────────────────────
    "wled": {
        "description": "WLED — прошивка для LED-лент (ESP32/ESP8266)",
        "examples": [
            {
                "name": "WLED_0.14.0_ESP32.bin",
                "url": ("https://github.com/Aircoookie/WLED/releases/download/"
                        "v0.14.0/WLED_0.14.0_ESP32.bin"),
                "desc": "WLED v0.14 для ESP32",
            },
            {
                "name": "WLED_0.14.0_ESP8266.bin",
                "url": ("https://github.com/Aircoookie/WLED/releases/download/"
                        "v0.14.0/WLED_0.14.0_ESP8266.bin"),
                "desc": "WLED v0.14 для ESP8266",
            },
        ],
    },

    # ── ESPHome ───────────────────────────────────────────────────────────────
    "esphome": {
        "description": "ESPHome — примеры конфигураций YAML",
        "examples": [
            {
                "name": "esphome_bme280.yaml",
                "url": ("https://raw.githubusercontent.com/esphome/esphome/"
                        "release/esphome/components/bme280/README.md"),
                "desc": "ESPHome BME280 (температура/влажность/давление)",
                "ext": ".yaml",
                "inline": (
                    "esphome:\n  name: argos_sensor\n\nesp8266:\n  board: esp01_1m\n\n"
                    "wifi:\n  ssid: \"YOUR_SSID\"\n  password: \"YOUR_PASS\"\n\n"
                    "sensor:\n  - platform: bme280\n    temperature:\n      name: \"Температура\"\n"
                    "    pressure:\n      name: \"Давление\"\n    humidity:\n      name: \"Влажность\"\n"
                    "    address: 0x76\n    update_interval: 60s\n"
                ),
            },
            {
                "name": "esphome_pulse_counter.yaml",
                "desc": "ESPHome Pulse Counter (счётчик импульсов)",
                "ext": ".yaml",
                "inline": (
                    "esphome:\n  name: argos_pulse\n\nesp32:\n  board: esp32dev\n\n"
                    "sensor:\n  - platform: pulse_counter\n    pin: GPIO4\n"
                    "    name: \"Пульс-счётчик\"\n    update_interval: 60s\n"
                ),
            },
            {
                "name": "esphome_health_ble.yaml",
                "desc": "ESPHome BLE Passive (пульс/шаги с Bluetooth браслета)",
                "ext": ".yaml",
                "inline": (
                    "esphome:\n  name: argos_health_ble\n\nesp32:\n  board: esp32dev\n\n"
                    "esp32_ble_tracker:\n\nsensor:\n"
                    "  - platform: xiaomi_lywsdcgq\n    mac_address: \"AA:BB:CC:DD:EE:FF\"\n"
                    "    temperature:\n      name: \"Температура\"\n"
                    "    humidity:\n      name: \"Влажность\"\n"
                    "  - platform: miot_miband\n    mac_address: \"AA:BB:CC:DD:EE:FF\"\n"
                    "    steps:\n      name: \"Шаги\"\n"
                    "    heart_rate:\n      name: \"Пульс\"\n"
                ),
            },
        ],
    },

    # ── Arduino ───────────────────────────────────────────────────────────────
    "arduino": {
        "description": "Arduino — скетчи примеров для различных задач",
        "examples": [
            {
                "name": "arduino_blink.ino",
                "desc": "Blink — мигание светодиодом",
                "ext": ".ino",
                "inline": (
                    "// Arduino Blink\nvoid setup() {\n  pinMode(LED_BUILTIN, OUTPUT);\n}\n\n"
                    "void loop() {\n  digitalWrite(LED_BUILTIN, HIGH); delay(1000);\n"
                    "  digitalWrite(LED_BUILTIN, LOW);  delay(1000);\n}\n"
                ),
            },
            {
                "name": "arduino_dht22.ino",
                "desc": "DHT22 — датчик температуры и влажности",
                "ext": ".ino",
                "inline": (
                    "#include <DHT.h>\n#define DHTPIN 2\n#define DHTTYPE DHT22\n"
                    "DHT dht(DHTPIN, DHTTYPE);\n\nvoid setup() {\n"
                    "  Serial.begin(115200);\n  dht.begin();\n}\n\n"
                    "void loop() {\n  float h = dht.readHumidity();\n"
                    "  float t = dht.readTemperature();\n"
                    "  Serial.print(\"T:\"); Serial.print(t);\n"
                    "  Serial.print(\" H:\"); Serial.println(h);\n  delay(2000);\n}\n"
                ),
            },
            {
                "name": "arduino_max30102_pulse.ino",
                "desc": "MAX30102 — датчик пульса и SpO2 (кислород крови)",
                "ext": ".ino",
                "inline": (
                    "#include <Wire.h>\n#include \"MAX30105.h\"\n#include \"heartRate.h\"\n\n"
                    "MAX30105 particleSensor;\nconst byte RATE_SIZE = 4;\n"
                    "byte rates[RATE_SIZE]; byte rateSpot = 0;\n"
                    "long lastBeat = 0; float beatsPerMinute; int beatAvg;\n\n"
                    "void setup() {\n  Serial.begin(115200);\n"
                    "  particleSensor.begin(Wire, I2C_SPEED_FAST);\n"
                    "  particleSensor.setup();\n"
                    "  particleSensor.setPulseAmplitudeRed(0x0A);\n}\n\n"
                    "void loop() {\n  long irValue = particleSensor.getIR();\n"
                    "  if (checkForBeat(irValue)) {\n"
                    "    long delta = millis() - lastBeat;\n    lastBeat = millis();\n"
                    "    beatsPerMinute = 60 / (delta / 1000.0);\n"
                    "    rates[rateSpot++] = (byte)beatsPerMinute;\n"
                    "    rateSpot %= RATE_SIZE;\n    beatAvg = 0;\n"
                    "    for (byte x = 0; x < RATE_SIZE; x++) beatAvg += rates[x];\n"
                    "    beatAvg /= RATE_SIZE;\n  }\n"
                    "  Serial.print(\"BPM=\"); Serial.print(beatsPerMinute);\n"
                    "  Serial.print(\" Avg=\"); Serial.println(beatAvg);\n  delay(20);\n}\n"
                ),
            },
            {
                "name": "arduino_mpu6050_steps.ino",
                "desc": "MPU6050 — акселерометр, шагомер",
                "ext": ".ino",
                "inline": (
                    "#include <Adafruit_MPU6050.h>\n#include <Adafruit_Sensor.h>\n"
                    "#include <Wire.h>\n\nAdafruit_MPU6050 mpu;\nint stepCount = 0;\n"
                    "float prevAcc = 0; const float THRESHOLD = 1.2;\n\n"
                    "void setup() {\n  Serial.begin(115200);\n"
                    "  mpu.begin();\n  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);\n}\n\n"
                    "void loop() {\n  sensors_event_t a, g, temp;\n"
                    "  mpu.getEvent(&a, &g, &temp);\n"
                    "  float acc = sqrt(a.acceleration.x * a.acceleration.x +\n"
                    "                   a.acceleration.y * a.acceleration.y +\n"
                    "                   a.acceleration.z * a.acceleration.z);\n"
                    "  if (acc > THRESHOLD && prevAcc <= THRESHOLD) stepCount++;\n"
                    "  prevAcc = acc;\n"
                    "  Serial.print(\"Steps: \"); Serial.println(stepCount);\n  delay(50);\n}\n"
                ),
            },
        ],
    },

    # ── MicroPython ───────────────────────────────────────────────────────────
    "micropython": {
        "description": "MicroPython — скрипты для ESP32/RP2040",
        "examples": [
            {
                "name": "mp_blink.py",
                "desc": "Blink (MicroPython)",
                "ext": ".py",
                "inline": (
                    "from machine import Pin\nfrom time import sleep\n\n"
                    "led = Pin(2, Pin.OUT)\nwhile True:\n"
                    "    led.on(); sleep(0.5)\n    led.off(); sleep(0.5)\n"
                ),
            },
            {
                "name": "mp_dht22.py",
                "desc": "DHT22 (MicroPython)",
                "ext": ".py",
                "inline": (
                    "import dht, machine, time\n"
                    "sensor = dht.DHT22(machine.Pin(4))\n"
                    "while True:\n    sensor.measure()\n"
                    "    print('T:', sensor.temperature(), 'H:', sensor.humidity())\n"
                    "    time.sleep(2)\n"
                ),
            },
            {
                "name": "mp_mqtt_sensor.py",
                "desc": "MQTT + датчик (MicroPython + umqtt.simple)",
                "ext": ".py",
                "inline": (
                    "from umqtt.simple import MQTTClient\nimport machine, network, time\n\n"
                    "wlan = network.WLAN(network.STA_IF)\nwlan.active(True)\n"
                    "wlan.connect('SSID', 'PASS')\nwhile not wlan.isconnected(): time.sleep(0.5)\n\n"
                    "c = MQTTClient('argos', '192.168.1.1')\nc.connect()\n"
                    "while True:\n    c.publish(b'argos/sensor', b'ok')\n    time.sleep(5)\n"
                ),
            },
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Загрузчик примеров
# ─────────────────────────────────────────────────────────────────────────────

class FirmwareExamplesLoader:
    """Загружает примеры прошивок из открытых источников."""

    def __init__(self):
        os.makedirs(EXAMPLES_DIR, exist_ok=True)

    # ── Публичный интерфейс ───────────────────────────────────────────────────

    def catalog(self) -> str:
        """Возвращает каталог доступных источников примеров."""
        lines = ["📚 КАТАЛОГ ПРИМЕРОВ ПРОШИВОК:"]
        for key, meta in SOURCES.items():
            count = len(meta["examples"])
            lines.append(f"  • {key:12s} — {meta['description']} ({count} примеров)")
        lines.append("\nКоманды:")
        lines.append("  примеры tasmota / wled / esphome / arduino / micropython")
        lines.append("  примеры список — скачанные файлы")
        return "\n".join(lines)

    def download(self, source_key: str, filter_topic: str = "") -> str:
        """Скачивает примеры из указанного источника."""
        source_key = source_key.lower().strip()
        meta = SOURCES.get(source_key)
        if meta is None:
            keys = ", ".join(SOURCES.keys())
            return f"❌ Источник не найден: {source_key}\nДоступные: {keys}"

        dest_dir = os.path.join(EXAMPLES_DIR, source_key)
        os.makedirs(dest_dir, exist_ok=True)

        results = [f"📥 Загрузка примеров [{source_key}] → {dest_dir}"]
        for ex in meta["examples"]:
            name = ex["name"]
            if filter_topic and filter_topic.lower() not in (
                    name.lower() + ex.get("desc", "").lower()):
                continue
            path = os.path.join(dest_dir, name)
            result = self._save_example(ex, path)
            results.append(f"  {result}")

        results.append(f"\n✅ Файлы в: {dest_dir}")
        results.append("Следующий шаг: прошивка список  или  прошивка анализ <файл>")
        return "\n".join(results)

    def list_downloaded(self) -> str:
        """Список всех скачанных примеров."""
        os.makedirs(EXAMPLES_DIR, exist_ok=True)
        lines = [f"📁 Скачанные примеры ({EXAMPLES_DIR}):"]
        total = 0
        for root, dirs, files in os.walk(EXAMPLES_DIR):
            dirs.sort()
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                rel   = os.path.relpath(fpath, EXAMPLES_DIR)
                size  = os.path.getsize(fpath)
                lines.append(f"  • {rel}  ({size // 1024 or '<1'} KB)")
                total += 1
        if total == 0:
            lines.append("  (пусто) — загрузи: примеры tasmota")
        else:
            lines.append(f"\nВсего: {total} файлов")
        return "\n".join(lines)

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _save_example(self, ex: dict, path: str) -> str:
        """Сохраняет один пример (из URL или inline-кода)."""
        name = ex["name"]
        desc = ex.get("desc", "")

        # Inline-контент (не требует сети)
        if "inline" in ex:
            try:
                mode = "w" if ex.get("ext", "") not in {".bin", ".uf2"} else "wb"
                with open(path, mode, encoding="utf-8" if "w" in mode else None) as f:
                    f.write(ex["inline"])
                return f"✅ {name} ({len(ex['inline'])} байт) — {desc}"
            except Exception as e:
                return f"❌ {name}: {e}"

        # Скачивание по URL
        url = ex.get("url")
        if not url:
            return f"⚠️ {name}: нет URL и нет inline"

        if not REQUESTS_OK:
            return f"⚠️ {name}: requests не установлен (pip install requests)"

        try:
            log.info("Загрузка %s...", url)
            r = _req.get(url, stream=True, timeout=20)
            if r.status_code != 200:
                return f"❌ {name}: HTTP {r.status_code}"
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            size = os.path.getsize(path)
            return f"✅ {name} ({size // 1024} KB) — {desc}"
        except Exception as e:
            log.warning("Ошибка загрузки %s: %s", name, e)
            return f"❌ {name}: {e}"

    def download_all(self) -> str:
        """Скачивает примеры из всех источников."""
        results = ["📥 Загрузка всех примеров..."]
        for key in SOURCES:
            results.append(self.download(key))
        return "\n\n".join(results)
