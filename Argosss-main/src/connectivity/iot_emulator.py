"""
iot_emulator.py — Эмуляторы IoT-устройств для тестирования Argos без физического железа.

Содержит:
  MQTTDevice  — базовый класс MQTT-устройства
  TempSensor  — эмулятор датчика температуры/влажности
  SmartPlug   — эмулятор умной розетки / реле
  RGBLight    — эмулятор RGB-светильника
  IotEmulatorManager — менеджер для запуска/остановки эмуляторов

Использование (команды Аргоса):
  запусти эмулятор [тип] [id]    — например: запусти эмулятор термометр greenhouse_01
  останови эмулятор [id]          — останови эмулятор greenhouse_01
  список эмуляторов               — показать активные эмуляторы
  эмуляторы статус                — то же самое
"""

import json
import random
import threading
import time
from src.argos_logger import get_logger

log = get_logger("argos.iot_emulator")

try:
    import paho.mqtt.client as mqtt_client
    MQTT_OK = True
except ImportError:
    mqtt_client = None
    MQTT_OK = False


# ─────────────────────────────────────────────────
# Базовый класс MQTT-устройства
# ─────────────────────────────────────────────────

class MQTTDevice:
    """Базовый класс для всех эмулируемых IoT-устройств."""

    def __init__(self, device_id: str, mqtt_host: str = "localhost", mqtt_port: int = 1883):
        self.device_id = device_id
        self.running = False
        self.state: dict = {}
        self._client = None
        self._host = mqtt_host
        self._port = mqtt_port

        if MQTT_OK:
            try:
                self._client = mqtt_client.Client()
                self._client.on_connect = self._on_connect
                self._client.on_message = self._on_message
                self._client.connect(mqtt_host, mqtt_port, 60)
                self._client.subscribe(f"argos/{device_id}/command/#")
                self._client.loop_start()
                self.running = True
                log.info("Эмулятор %s подключён к MQTT %s:%s", device_id, mqtt_host, mqtt_port)
            except Exception as e:
                log.warning("Эмулятор %s: нет MQTT (%s) — работаю без брокера", device_id, e)
                self.running = True
        else:
            log.info("Эмулятор %s: paho-mqtt не установлен — работаю без MQTT", device_id)
            self.running = True

    def _on_connect(self, client, userdata, flags, rc):
        log.debug("[%s] MQTT connected (rc=%s)", self.device_id, rc)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        self.handle_command(topic, payload)

    def handle_command(self, topic: str, payload: str):
        """Переопределяется в дочерних классах."""

    def publish_state(self):
        """Публикует текущее состояние в MQTT-топик."""
        if self._client:
            try:
                self._client.publish(
                    f"argos/{self.device_id}/state",
                    json.dumps(self.state, ensure_ascii=False),
                )
            except Exception as e:
                log.debug("Публикация состояния %s: %s", self.device_id, e)

    def stop(self):
        self.running = False
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass

    def get_info(self) -> dict:
        return {
            "id": self.device_id,
            "type": self.__class__.__name__,
            "state": self.state,
            "running": self.running,
        }


# ─────────────────────────────────────────────────
# Датчик температуры/влажности
# ─────────────────────────────────────────────────

class TempSensor(MQTTDevice):
    """Эмулятор датчика температуры и влажности."""

    DEVICE_TYPE = "sensor"

    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, **kwargs)
        self.state = {"temperature": 22.5, "humidity": 60.0}
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()

    def _update_loop(self):
        while self.running:
            self.state["temperature"] += random.uniform(-0.5, 0.5)
            self.state["humidity"] += random.uniform(-1.0, 1.0)
            self.state["temperature"] = round(max(15.0, min(35.0, self.state["temperature"])), 2)
            self.state["humidity"] = round(max(30.0, min(90.0, self.state["humidity"])), 2)
            self.publish_state()
            time.sleep(5)

    def handle_command(self, topic: str, payload: str):
        # Датчик только публикует данные, команд не принимает
        pass


# ─────────────────────────────────────────────────
# Умная розетка / реле
# ─────────────────────────────────────────────────

class SmartPlug(MQTTDevice):
    """Эмулятор умной розетки (реле, управляемый выключатель)."""

    DEVICE_TYPE = "actuator"

    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, **kwargs)
        self.state = {"power": "off", "current": 0.0, "voltage": 220.0}
        self.publish_state()

    def handle_command(self, topic: str, payload: str):
        if topic.endswith("/set"):
            if payload.lower() in ("on", "off"):
                self.state["power"] = payload.lower()
                self.state["current"] = round(random.uniform(0.5, 2.0), 2) if self.state["power"] == "on" else 0.0
                self.publish_state()
                log.info("[%s] power → %s", self.device_id, payload)
        elif topic.endswith("/set/brightness"):
            try:
                self.state["brightness"] = max(0, min(100, int(payload)))
                self.publish_state()
            except ValueError:
                pass

    def turn_on(self):
        self.handle_command(f"argos/{self.device_id}/command/set", "on")

    def turn_off(self):
        self.handle_command(f"argos/{self.device_id}/command/set", "off")


# ─────────────────────────────────────────────────
# RGB-светильник
# ─────────────────────────────────────────────────

class RGBLight(MQTTDevice):
    """Эмулятор RGB-светильника с управлением цветом и яркостью."""

    DEVICE_TYPE = "actuator"

    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, **kwargs)
        self.state = {"power": "off", "color": "#FFFFFF", "brightness": 100}
        self.publish_state()

    def handle_command(self, topic: str, payload: str):
        if topic.endswith("/set/power"):
            self.state["power"] = payload.lower()
        elif topic.endswith("/set/color"):
            if payload.startswith("#") and len(payload) == 7:
                self.state["color"] = payload
        elif topic.endswith("/set/brightness"):
            try:
                self.state["brightness"] = max(0, min(100, int(payload)))
            except ValueError:
                pass
        self.publish_state()
        log.info("[%s] %s", self.device_id, self.state)


# ─────────────────────────────────────────────────
# Менеджер эмуляторов
# ─────────────────────────────────────────────────

_DEVICE_TYPES = {
    "термометр": TempSensor,
    "tempsensor": TempSensor,
    "датчик": TempSensor,
    "sensor": TempSensor,
    "розетка": SmartPlug,
    "smartplug": SmartPlug,
    "plug": SmartPlug,
    "реле": SmartPlug,
    "relay": SmartPlug,
    "лампа": RGBLight,
    "rgblight": RGBLight,
    "light": RGBLight,
    "свет": RGBLight,
}


class IotEmulatorManager:
    """Менеджер IoT-эмуляторов: запуск, остановка, статус."""

    def __init__(self, mqtt_host: str = "localhost", mqtt_port: int = 1883):
        self._devices: dict[str, MQTTDevice] = {}
        self._host = mqtt_host
        self._port = mqtt_port

    # ──────────────────────────────────────────────
    # Публичный API
    # ──────────────────────────────────────────────

    def start(self, device_type: str, device_id: str) -> str:
        """Запустить эмулятор указанного типа."""
        cls = _DEVICE_TYPES.get(device_type.lower())
        if cls is None:
            types = ", ".join(sorted({v.__name__ for v in _DEVICE_TYPES.values()}))
            return f"❌ Неизвестный тип устройства '{device_type}'. Доступны: {types}"
        if device_id in self._devices:
            return f"⚠️ Эмулятор '{device_id}' уже запущен."
        try:
            dev = cls(device_id, mqtt_host=self._host, mqtt_port=self._port)
            self._devices[device_id] = dev
            return (
                f"✅ Эмулятор {cls.__name__} '{device_id}' запущен.\n"
                f"   MQTT: {self._host}:{self._port}\n"
                f"   Топик состояния: argos/{device_id}/state\n"
                f"   Топик команд:    argos/{device_id}/command/#"
            )
        except Exception as e:
            return f"❌ Ошибка запуска эмулятора '{device_id}': {e}"

    def stop(self, device_id: str) -> str:
        """Остановить эмулятор."""
        dev = self._devices.pop(device_id, None)
        if dev is None:
            return f"⚠️ Эмулятор '{device_id}' не найден."
        dev.stop()
        return f"🛑 Эмулятор '{device_id}' остановлен."

    def stop_all(self) -> str:
        """Остановить все эмуляторы."""
        if not self._devices:
            return "Нет активных эмуляторов."
        ids = list(self._devices.keys())
        for dev in self._devices.values():
            dev.stop()
        self._devices.clear()
        return f"🛑 Остановлено {len(ids)} эмулятор(ов): {', '.join(ids)}"

    def status(self) -> str:
        """Статус всех активных эмуляторов."""
        if not self._devices:
            return "📭 Нет активных эмуляторов. Запусти: запусти эмулятор [тип] [id]"
        lines = [f"🤖 Активных эмуляторов: {len(self._devices)}"]
        for dev in self._devices.values():
            info = dev.get_info()
            lines.append(
                f"  • [{info['type']}] {info['id']} — {json.dumps(info['state'], ensure_ascii=False)}"
            )
        return "\n".join(lines)

    def send_command(self, device_id: str, command: str, value: str = "") -> str:
        """Отправить команду эмулятору напрямую (без MQTT)."""
        dev = self._devices.get(device_id)
        if dev is None:
            return f"⚠️ Эмулятор '{device_id}' не найден."
        topic = f"argos/{device_id}/command/{command}"
        dev.handle_command(topic, value)
        return f"✅ Команда '{command}={value}' отправлена устройству '{device_id}'."

    def help_text(self) -> str:
        """Справка по эмуляторам."""
        return (
            "🤖 **Эмуляторы IoT-устройств**\n"
            "Команды:\n"
            "  запусти эмулятор [тип] [id]   — типы: термометр, розетка, лампа\n"
            "  останови эмулятор [id]         — остановить конкретный\n"
            "  останови все эмуляторы         — остановить все\n"
            "  список эмуляторов              — показать активные\n"
            "  эмулятор команда [id] [cmd] [val] — отправить команду устройству\n\n"
            "Примеры:\n"
            "  запусти эмулятор термометр теплица_01\n"
            "  запусти эмулятор розетка гараж_розетка\n"
            "  запусти эмулятор лампа спальня_лампа\n"
            "  эмулятор команда гараж_розетка set on\n"
            "  останови эмулятор теплица_01"
        )
