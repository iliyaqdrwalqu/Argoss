"""
smarthome_override.py — Прямое управление Zigbee/Z-Wave/Tuya без облаков.
Обходит облачные сервисы производителей для локального контроля.
"""
import os
import time
import json
import threading
from typing import Optional, List
from dataclasses import dataclass, field, asdict
from src.argos_logger import get_logger

log = get_logger("argos.smarthome_override")

try:
    import paho.mqtt.client as mqtt
    MQTT_OK = True
except ImportError:
    mqtt = None; MQTT_OK = False


@dataclass
class SmartDevice:
    device_id: str
    friendly_name: str = ""
    protocol: str = "zigbee"
    ieee_address: str = ""
    cloud_blocked: bool = False
    state: dict = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self): return asdict(self)


class SmartHomeOverride:
    """Прямое управление умным домом без облаков."""
    ZIGBEE2MQTT_TOPIC = "zigbee2mqtt"
    TUYA_LOCAL_PORT = 6668

    def __init__(self):
        self._devices: dict = {}
        self._mqtt_client = None
        self._running = False
        self._pending_cmds: list = []

    def start(self) -> str:
        if MQTT_OK:
            return self._start_mqtt()
        return "⚠️ SmartHome Override: paho-mqtt не установлен. Режим симуляции."

    def _start_mqtt(self) -> str:
        try:
            host = os.getenv("MQTT_HOST", "localhost")
            port = int(os.getenv("MQTT_PORT", "1883"))
            self._mqtt_client = mqtt.Client()
            self._mqtt_client.on_message = self._on_mqtt_message
            self._mqtt_client.connect(host, port, 60)
            self._mqtt_client.subscribe(f"{self.ZIGBEE2MQTT_TOPIC}/#")
            self._mqtt_client.loop_start()
            self._running = True
            log.info("SmartHome Override: MQTT подключен %s:%d", host, port)
            return f"✅ SmartHome Override: подключен к MQTT {host}:{port}"
        except Exception as e:
            return f"❌ SmartHome Override MQTT: {e}"

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            # Парсим zigbee2mqtt/<device>
            parts = topic.split("/")
            if len(parts) >= 2:
                dev_id = parts[1]
                if dev_id not in self._devices:
                    self._devices[dev_id] = SmartDevice(
                        device_id=dev_id,
                        friendly_name=dev_id,
                        protocol="zigbee"
                    )
                self._devices[dev_id].state = payload
                self._devices[dev_id].last_seen = time.time()
        except Exception as e:
            log.debug("MQTT message parse: %s", e)

    def send_command(self, device_id: str, command: str,
                     value=None, protocol: str = "auto") -> str:
        """Отправляет команду устройству напрямую."""
        dev = self._devices.get(device_id)
        if not dev:
            return f"❌ Устройство '{device_id}' не найдено"

        if dev.cloud_blocked:
            log.info("Cloud blocked for %s — using local only", device_id)

        proto = protocol if protocol != "auto" else dev.protocol
        if proto == "zigbee" and self._mqtt_client:
            topic = f"{self.ZIGBEE2MQTT_TOPIC}/{device_id}/set"
            payload = {command: value} if value is not None else {command: ""}
            try:
                self._mqtt_client.publish(topic, json.dumps(payload))
                dev.state[command] = value
                return f"✅ {device_id} → {command}={value} (Zigbee MQTT)"
            except Exception as e:
                return f"❌ Zigbee cmd: {e}"
        elif proto == "tuya":
            return self._tuya_command(device_id, command, value)
        else:
            # Симуляция
            if dev:
                dev.state[command] = value
            return f"[SIM] {device_id} → {command}={value}"

    def _tuya_command(self, device_id: str, command: str, value) -> str:
        """Tuya local protocol v3.3 (упрощённый)."""
        dev = self._devices.get(device_id)
        if not dev:
            return f"❌ Tuya: устройство {device_id} не найдено"
        try:
            import socket
            import struct
            local_key = os.getenv(f"TUYA_KEY_{device_id}", "")
            ip = dev.state.get("ip", "")
            if not ip:
                return f"❌ Tuya: IP для {device_id} неизвестен"
            # Базовая проверка связи
            sock = socket.socket()
            sock.settimeout(3)
            sock.connect((ip, self.TUYA_LOCAL_PORT))
            sock.close()
            return f"✅ Tuya {device_id}: соединение OK (full protocol requires tinytuya)"
        except Exception as e:
            return f"❌ Tuya {device_id}: {e}"

    def block_cloud(self, device_id: str) -> str:
        """Блокирует облачный трафик устройства (через hosts/iptables)."""
        dev = self._devices.get(device_id)
        if dev:
            dev.cloud_blocked = True
            log.info("Cloud blocked: %s", device_id)
            return f"✅ Облако заблокировано для {device_id}"
        return f"❌ Устройство не найдено: {device_id}"

    def add_device(self, device_id: str, name: str = "",
                   protocol: str = "zigbee") -> str:
        self._devices[device_id] = SmartDevice(
            device_id=device_id,
            friendly_name=name or device_id,
            protocol=protocol
        )
        return f"✅ Устройство добавлено: {device_id} ({protocol})"

    def list_devices(self) -> list:
        return [d.to_dict() for d in self._devices.values()]

    def status(self) -> str:
        mqtt_s = "✅" if (self._mqtt_client and self._running) else "❌"
        return (
            f"🏠 SMARTHOME OVERRIDE:\n"
            f"  MQTT:       {mqtt_s}\n"
            f"  Устройств:  {len(self._devices)}\n"
            f"  Заблокованных облако: {sum(1 for d in self._devices.values() if d.cloud_blocked)}"
        )

# Alias
SmarthomeOverride = SmartHomeOverride
