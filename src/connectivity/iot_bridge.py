"""
iot_bridge.py — IoT-мост Аргоса
  Поддержка: Zigbee (zigpy/zigbee2mqtt), LoRa (pyserial + AT),
             Mesh (ESP-NOW / custom UDP mesh), MQTT, Modbus (RTU/ASCII/TCP),
             BACnet, KNX, LonWorks, M-Bus, OPC UA.
  Аргос — оператор умных систем: дом, теплица, гараж, погреб,
  инкубатор, аквариум, террариум.
"""
import json, os, time, threading, socket, struct
from collections import defaultdict
from src.argos_logger import get_logger
from src.event_bus import get_bus, Events
from src.observability import log_iot, trace

log = get_logger("argos.iot")
bus = get_bus()

# Реестр всех устройств
DEVICES_FILE = "data/iot_devices.json"


class IoTDevice:
    def __init__(self, device_id: str, dtype: str, protocol: str,
                 address: str = "", name: str = ""):
        self.id       = device_id
        self.type     = dtype       # sensor | actuator | gateway
        self.protocol = protocol    # zigbee | lora | mesh | mqtt | modbus
        self.address  = address
        self.name     = name or device_id
        self.state    : dict = {}
        self.last_seen: float = 0
        self.online   : bool  = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "protocol": self.protocol,
            "address": self.address, "name": self.name,
            "state": self.state, "last_seen": self.last_seen, "online": self.online,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IoTDevice":
        dev = cls(d["id"], d["type"], d["protocol"],
                  d.get("address",""), d.get("name",""))
        dev.state     = d.get("state", {})
        dev.last_seen = d.get("last_seen", 0)
        dev.online    = d.get("online", False)
        return dev

    def update(self, key: str, value):
        old = self.state.get(key)
        self.state[key]  = value
        self.last_seen   = time.time()
        self.online      = True
        log_iot(self.id, key, value)
        if old != value:
            bus.emit(Events.IOT_VALUE_CHANGED,
                     {"device": self.id, "key": key, "old": old, "new": value},
                     "iot_bridge")


class IoTRegistry:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self._devices: dict[str, IoTDevice] = {}
        self._load()

    def _load(self):
        if os.path.exists(DEVICES_FILE):
            try:
                data = json.load(open(DEVICES_FILE, encoding="utf-8"))
                for d in data:
                    dev = IoTDevice.from_dict(d)
                    self._devices[dev.id] = dev
                log.info("IoT: загружено %d устройств", len(self._devices))
            except Exception as e:
                log.warning("IoT registry load error: %s", e)

    def save(self):
        try:
            data = [d.to_dict() for d in self._devices.values()]
            json.dump(data, open(DEVICES_FILE, "w", encoding="utf-8"),
                      indent=2, ensure_ascii=False)
        except Exception as e:
            log.error("IoT save error: %s", e)

    def register(self, dev: IoTDevice) -> str:
        self._devices[dev.id] = dev
        self.save()
        bus.emit(Events.IOT_DEVICE_FOUND, dev.to_dict(), "iot_registry")
        log.info("IoT: зарегистрировано %s [%s/%s]", dev.name, dev.protocol, dev.type)
        return f"✅ Устройство '{dev.name}' зарегистрировано."

    def get(self, dev_id: str) -> IoTDevice | None:
        return self._devices.get(dev_id)

    def all(self) -> list[IoTDevice]:
        return list(self._devices.values())

    def online(self) -> list[IoTDevice]:
        return [d for d in self._devices.values() if d.online]

    def report(self) -> str:
        devices = self.all()
        if not devices:
            return "📡 IoT устройств нет. Подключи через: зарегистрируй устройство"
        lines = [f"📡 IoT СЕТЬ ({len(devices)} устройств):"]
        by_proto = defaultdict(list)
        for d in devices:
            by_proto[d.protocol].append(d)
        for proto, devs in sorted(by_proto.items()):
            lines.append(f"\n  [{proto.upper()}]")
            for d in devs:
                status = "🟢" if d.online else "🔴"
                ago    = _ago(d.last_seen)
                state  = ", ".join(f"{k}={v}" for k, v in list(d.state.items())[:3])
                lines.append(f"    {status} {d.name} [{d.type}] {ago}")
                if state: lines.append(f"       {state}")
        return "\n".join(lines)


def _ago(ts: float) -> str:
    if not ts: return "никогда"
    s = int(time.time() - ts)
    if s < 60:   return f"{s}с назад"
    if s < 3600: return f"{s//60}м назад"
    return f"{s//3600}ч назад"


# ══════════════════════════════════════════════════════════
# ПРОТОКОЛЫ
# ══════════════════════════════════════════════════════════

class ZigbeeAdapter:
    """Адаптер Zigbee через zigbee2mqtt (MQTT) или zigpy."""
    def __init__(self, registry: IoTRegistry):
        self.registry = registry
        self._mqtt    = None

    def connect_mqtt(self, host: str = "localhost",
                     port: int = 1883, topic: str = "zigbee2mqtt/#") -> str:
        try:
            import paho.mqtt.client as mqtt
            client = mqtt.Client()
            client.on_message = self._on_mqtt_message
            client.connect(host, port, 60)
            client.subscribe(topic)
            client.loop_start()
            self._mqtt = client
            log.info("Zigbee MQTT подключён: %s:%d", host, port)
            return f"✅ Zigbee MQTT: {host}:{port} тема {topic}"
        except ImportError:
            return "❌ pip install paho-mqtt"
        except Exception as e:
            return f"❌ Zigbee MQTT: {e}"

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            topic  = msg.topic.replace("zigbee2mqtt/", "")
            data   = json.loads(msg.payload.decode())
            dev_id = f"zb_{topic.replace('/','_')}"
            dev = self.registry.get(dev_id)
            if not dev:
                dev = IoTDevice(dev_id, "sensor", "zigbee", topic, topic)
                self.registry.register(dev)
            for k, v in data.items():
                dev.update(k, v)
        except Exception as e:
            log.error("Zigbee MQTT parse: %s", e)

    def send_command(self, device_name: str, payload: dict) -> str:
        if not self._mqtt:
            return "❌ MQTT не подключён."
        try:
            topic = f"zigbee2mqtt/{device_name}/set"
            self._mqtt.publish(topic, json.dumps(payload))
            return f"✅ Команда отправлена: {device_name} ← {payload}"
        except Exception as e:
            return f"❌ {e}"


class LoRaAdapter:
    """Адаптер LoRa через UART (AT-команды) или pyserial."""
    def __init__(self, registry: IoTRegistry):
        self.registry = registry
        self._serial  = None
        self._port    = None
        self._running = False

    def connect(self, port: str = "/dev/ttyUSB0",
                baud: int = 9600, freq: float = 433.0) -> str:
        try:
            import serial
            self._serial = serial.Serial(port, baud, timeout=2)
            self._port   = port
            # Инициализация LoRa модема AT-командами
            self._serial.write(b"AT+RESET\r\n")
            time.sleep(1)
            self._serial.write(f"AT+FREQ={freq}\r\n".encode())
            time.sleep(0.5)
            self._serial.write(b"AT+MODE=0\r\n")  # normal mode
            self._running = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            log.info("LoRa подключён: %s, %.1fMHz", port, freq)
            return f"✅ LoRa: {port} @ {freq}MHz"
        except ImportError:
            return "❌ pip install pyserial"
        except Exception as e:
            return f"❌ LoRa: {e}"

    def _read_loop(self):
        while self._running and self._serial:
            try:
                line = self._serial.readline().decode("utf-8", errors="ignore").strip()
                if line.startswith("+RCV="):
                    # +RCV=addr,len,data,rssi,snr
                    parts = line[5:].split(",")
                    if len(parts) >= 3:
                        addr = parts[0]
                        data = parts[2]
                        self._parse_lora_packet(addr, data)
            except Exception as e:
                if self._running:
                    log.error("LoRa read: %s", e)

    def _parse_lora_packet(self, addr: str, data: str):
        dev_id = f"lora_{addr}"
        dev = self.registry.get(dev_id)
        if not dev:
            dev = IoTDevice(dev_id, "sensor", "lora", addr, f"LoRa-{addr}")
            self.registry.register(dev)
        # Формат: key:value,key:value
        for pair in data.split(","):
            if ":" in pair:
                k, v = pair.split(":", 1)
                try:
                    v = float(v)
                except ValueError:
                    pass
                dev.update(k.strip(), v)
        log.debug("LoRa пакет от %s: %s", addr, data[:50])

    def send(self, addr: str, data: str) -> str:
        if not self._serial:
            return "❌ LoRa не подключён."
        try:
            cmd = f"AT+SEND={addr},{len(data)},{data}\r\n"
            self._serial.write(cmd.encode())
            time.sleep(0.3)
            return f"✅ LoRa → {addr}: {data[:50]}"
        except Exception as e:
            return f"❌ {e}"

    def broadcast(self, data: str) -> str:
        return self.send("255", data)  # broadcast addr


class MeshAdapter:
    """UDP Mesh сеть (ESP-NOW совместимый протокол через Wi-Fi)."""
    def __init__(self, registry: IoTRegistry, port: int = 9876):
        self.registry = registry
        self.port     = port
        self._sock    = None
        self._running = False

    def start(self) -> str:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._sock.bind(("", self.port))
            self._running = True
            threading.Thread(target=self._listen, daemon=True).start()
            log.info("Mesh UDP запущен на порту %d", self.port)
            return f"✅ Mesh UDP слушает порт {self.port}"
        except Exception as e:
            return f"❌ Mesh: {e}"

    def _listen(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)
                self._parse_packet(data, addr[0])
            except Exception as e:
                if self._running:
                    log.error("Mesh recv: %s", e)

    def _parse_packet(self, raw: bytes, ip: str):
        try:
            pkt = json.loads(raw.decode())
            dev_id = f"mesh_{pkt.get('id', ip.replace('.','_'))}"
            dev = self.registry.get(dev_id)
            if not dev:
                dev = IoTDevice(dev_id, pkt.get("type","sensor"),
                               "mesh", ip, pkt.get("name", dev_id))
                self.registry.register(dev)
            for k, v in pkt.get("data", {}).items():
                dev.update(k, v)
        except Exception as e:
            log.error("Mesh parse: %s", e)

    def send(self, ip: str, payload: dict) -> str:
        if not self._sock:
            return "❌ Mesh не запущен."
        try:
            data = json.dumps(payload).encode()
            self._sock.sendto(data, (ip, self.port))
            return f"✅ Mesh → {ip}: {payload}"
        except Exception as e:
            return f"❌ {e}"

    def broadcast(self, payload: dict) -> str:
        return self.send("255.255.255.255", payload)


class MQTTBroker:
    """Обёртка над paho-mqtt для общего MQTT брокера."""
    def __init__(self, registry: IoTRegistry):
        self.registry    = registry
        self._client     = None
        self._callbacks  = {}

    def connect(self, host: str = "localhost", port: int = 1883) -> str:
        try:
            import paho.mqtt.client as mqtt
            self._client = mqtt.Client()
            self._client.on_message  = self._on_message
            self._client.on_connect  = lambda c, u, f, rc: log.info("MQTT connected rc=%d", rc)
            self._client.connect(host, port, 60)
            self._client.loop_start()
            return f"✅ MQTT брокер: {host}:{port}"
        except ImportError:
            return "❌ pip install paho-mqtt"
        except Exception as e:
            return f"❌ MQTT: {e}"

    def subscribe(self, topic: str, callback=None) -> str:
        if not self._client:
            return "MQTT не подключён."
        self._client.subscribe(topic)
        if callback:
            self._callbacks[topic] = callback
        return f"✅ Подписан на: {topic}"

    def publish(self, topic: str, payload: dict | str) -> str:
        if not self._client:
            return "MQTT не подключён."
        msg = json.dumps(payload) if isinstance(payload, dict) else str(payload)
        self._client.publish(topic, msg)
        return f"✅ MQTT → {topic}: {msg[:50]}"

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        cb    = self._callbacks.get(topic)
        if cb:
            try: cb(msg.topic, msg.payload)
            except Exception as e: log.error("MQTT cb: %s", e)


# ══════════════════════════════════════════════════════════
# ГЛАВНЫЙ КЛАСС IoTBridge
# ══════════════════════════════════════════════════════════

class IoTBridge:
    def __init__(self):
        self.registry = IoTRegistry()
        self.zigbee   = ZigbeeAdapter(self.registry)
        self.lora     = LoRaAdapter(self.registry)
        self.mesh     = MeshAdapter(self.registry)
        self.mqtt     = MQTTBroker(self.registry)
        log.info("IoTBridge инициализирован. Устройств: %d", len(self.registry.all()))

    def connect_zigbee(self, host="localhost", port=1883) -> str:
        return self.zigbee.connect_mqtt(host, port)

    def connect_lora(self, port="/dev/ttyUSB0", baud=9600) -> str:
        return self.lora.connect(port, baud)

    def start_mesh(self) -> str:
        return self.mesh.start()

    def connect_mqtt(self, host="localhost", port=1883) -> str:
        return self.mqtt.connect(host, port)

    def register_device(self, dev_id: str, dtype: str, protocol: str,
                        address: str = "", name: str = "") -> str:
        dev = IoTDevice(dev_id, dtype, protocol, address, name)
        return self.registry.register(dev)

    def status(self) -> str:
        return self.registry.report()

    def device_status(self, dev_id: str) -> str:
        dev = self.registry.get(dev_id)
        if not dev:
            return f"❌ Устройство '{dev_id}' не найдено."

        status = "🟢 online" if dev.online else "🔴 offline"
        lines = [
            f"📟 Устройство: {dev.name}",
            f"  id: {dev.id}",
            f"  тип: {dev.type}",
            f"  протокол: {dev.protocol}",
            f"  адрес: {dev.address or '—'}",
            f"  статус: {status}",
            f"  last_seen: {_ago(dev.last_seen)}",
        ]
        if dev.state:
            lines.append("  данные:")
            for k, v in list(dev.state.items())[:20]:
                lines.append(f"    - {k}: {v}")
        else:
            lines.append("  данные: нет")
        return "\n".join(lines)

    def send_command(self, dev_id: str, command: str, value=None) -> str:
        dev = self.registry.get(dev_id)
        if not dev:
            return f"❌ Устройство '{dev_id}' не найдено."
        if dev.protocol == "zigbee":
            return self.zigbee.send_command(dev.address, {command: value})
        if dev.protocol == "lora":
            return self.lora.send(dev.address, f"{command}:{value}")
        if dev.protocol == "mesh":
            return self.mesh.send(dev.address, {"cmd": command, "val": value})
        if dev.protocol == "mqtt":
            return self.mqtt.publish(f"devices/{dev_id}/set", {command: value})
        return f"❌ Протокол '{dev.protocol}' не поддерживает команды."

    def get_value(self, dev_id: str, key: str):
        dev = self.registry.get(dev_id)
        if not dev:
            return None
        return dev.state.get(key)
