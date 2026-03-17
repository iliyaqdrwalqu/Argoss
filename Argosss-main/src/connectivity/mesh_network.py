"""
mesh_network.py — Mesh-сеть: Zigbee, LoRa, WiFi Mesh
  Аргос как центральный оператор и gateway-менеджер.
  Поддержка: Zigbee (через zigpy/zigbee2mqtt), LoRa (sx127x/sx126x),
             WiFi Mesh (ESP-NOW, Meshtastic), Z-Wave.
  Прошивка gateway прямо из Аргоса.
"""
import os
import json
import threading
import time
from typing import Any

try:
    import serial
except ImportError:
    serial = None

from src.argos_logger import get_logger
from src.connectivity.event_bus import bus, EventType

log = get_logger("argos.mesh")

GATEWAY_DIR = "assets/firmware/gateways"
DEVICES_DB  = "config/mesh_devices.json"


class MeshDevice:
    def __init__(self, dev_id: str, protocol: str, addr: str,
                 name: str = "", room: str = "", role: str = "sensor"):
        self.id       = dev_id
        self.protocol = protocol   # zigbee | lora | wifi | zwave
        self.addr     = addr
        self.name     = name or dev_id
        self.room     = room
        self.role     = role       # sensor | actuator | gateway | coordinator
        self.online   = False
        self.last_seen = 0.0
        self.data     = {}         # последние данные

    def to_dict(self) -> dict:
        return {
            "id": self.id, "protocol": self.protocol, "addr": self.addr,
            "name": self.name, "room": self.room, "role": self.role,
            "online": self.online, "last_seen": self.last_seen,
            "data": self.data,
        }


class MeshNetwork:
    """Единый менеджер всех mesh-протоколов."""

    def __init__(self):
        self.devices: dict[str, MeshDevice] = {}
        self._bridges: dict[str, "ProtocolBridge"] = {}
        self._running = False
        self._load_devices()

    # ── УСТРОЙСТВА ────────────────────────────────────────
    def _load_devices(self):
        if os.path.exists(DEVICES_DB):
            try:
                data = json.load(open(DEVICES_DB, encoding="utf-8"))
                for d in data:
                    dev = MeshDevice(**d)
                    self.devices[dev.id] = dev
                log.info("Mesh: загружено %d устройств", len(self.devices))
            except Exception as e:
                log.error("Mesh load error: %s", e)

    def _save_devices(self):
        os.makedirs("config", exist_ok=True)
        data = [d.to_dict() for d in self.devices.values()]
        json.dump(data, open(DEVICES_DB, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)

    def add_device(self, dev_id: str, protocol: str, addr: str,
                   name: str = "", room: str = "", role: str = "sensor") -> str:
        dev = MeshDevice(dev_id, protocol, addr, name, room, role)
        self.devices[dev_id] = dev
        self._save_devices()
        bus.publish(EventType.DEVICE_ONLINE, dev.to_dict(), "mesh")
        log.info("Устройство добавлено: %s (%s)", name or dev_id, protocol)
        return f"✅ Устройство добавлено: {name or dev_id} [{protocol}] @ {addr}"

    def remove_device(self, dev_id: str) -> str:
        if dev_id in self.devices:
            name = self.devices[dev_id].name
            del self.devices[dev_id]
            self._save_devices()
            return f"🗑️ Устройство удалено: {name}"
        return f"❌ Устройство не найдено: {dev_id}"

    def update_device_data(self, dev_id: str, data: dict):
        if dev_id in self.devices:
            self.devices[dev_id].data      = {**self.devices[dev_id].data, **data}
            self.devices[dev_id].online    = True
            self.devices[dev_id].last_seen = time.time()
            bus.publish(EventType.SENSOR_UPDATE, {"id": dev_id, "data": data}, "mesh")

    # ── ПРОТОКОЛЫ ─────────────────────────────────────────
    def start_zigbee(self, port: str = "/dev/ttyUSB0",
                     baud: int = 115200) -> str:
        bridge = ZigbeeBridge(port, baud, self)
        result = bridge.start()
        if "✅" in result:
            self._bridges["zigbee"] = bridge
        return result

    def start_lora(self, port: str = "/dev/ttyUSB1",
                   baud: int = 9600) -> str:
        bridge = LoRaBridge(port, baud, self)
        result = bridge.start()
        if "✅" in result:
            self._bridges["lora"] = bridge
        return result

    def start_wifi_mesh(self, ssid: str = "ArgosNet") -> str:
        bridge = WiFiMeshBridge(ssid, self)
        result = bridge.start()
        if "✅" in result:
            self._bridges["wifi"] = bridge
        return result

    # ── КОМАНДЫ ───────────────────────────────────────────
    def send_command(self, dev_id: str, command: str,
                     value: Any = None) -> str:
        if dev_id not in self.devices:
            return f"❌ Устройство не найдено: {dev_id}"
        dev     = self.devices[dev_id]
        bridge  = self._bridges.get(dev.protocol)
        if not bridge:
            return f"❌ Bridge для {dev.protocol} не запущен"
        return bridge.send(dev.addr, command, value)

    def broadcast(self, protocol: str, command: str,
                  value: Any = None) -> str:
        bridge = self._bridges.get(protocol)
        if not bridge:
            return f"❌ Bridge {protocol} не запущен"
        results = []
        for dev in self.devices.values():
            if dev.protocol == protocol:
                r = bridge.send(dev.addr, command, value)
                results.append(f"  {dev.name}: {r}")
        return f"📡 Broadcast [{protocol}]:\n" + "\n".join(results)

    # ── ОТЧЁТ ─────────────────────────────────────────────
    def status_report(self) -> str:
        if not self.devices:
            return "📭 Mesh-сеть: устройств нет.\n  Добавь: аргос, добавь устройство zigbee [id] [адрес] [имя] [комната]"
        lines = [f"📡 MESH-СЕТЬ ({len(self.devices)} устройств):"]
        by_proto = {}
        for dev in self.devices.values():
            by_proto.setdefault(dev.protocol, []).append(dev)
        for proto, devs in sorted(by_proto.items()):
            lines.append(f"\n  [{proto.upper()}]")
            for dev in devs:
                ago     = int(time.time() - dev.last_seen) if dev.last_seen else 0
                status  = "🟢" if dev.online and ago < 120 else "🔴"
                last    = f"{ago}с назад" if dev.last_seen else "никогда"
                data_s  = ", ".join(f"{k}={v}" for k, v in list(dev.data.items())[:3])
                lines.append(f"    {status} {dev.name:20s} [{dev.room}] addr={dev.addr} | {data_s}")
        for proto, bridge in self._bridges.items():
            lines.append(f"\n  Bridge {proto}: {bridge.status()}")
        return "\n".join(lines)

    # ── ПРОШИВКА GATEWAY ──────────────────────────────────
    def flash_gateway(self, port: str, firmware: str = "zigbee_gateway") -> str:
        """Прошивает gateway через COM-порт используя esptool/avrdude."""
        fw_path = f"{GATEWAY_DIR}/{firmware}.bin"
        if not os.path.exists(fw_path):
            return (f"❌ Прошивка не найдена: {fw_path}\n"
                    f"  Доступные: {self._list_firmware()}")
        return GatewayFlasher().flash(port, fw_path)

    def _list_firmware(self) -> str:
        os.makedirs(GATEWAY_DIR, exist_ok=True)
        files = [f[:-4] for f in os.listdir(GATEWAY_DIR)
                 if f.endswith(".bin")]
        return ", ".join(files) if files else "нет (положи .bin в assets/firmware/gateways/)"


# ── BRIDGES ───────────────────────────────────────────────


class ZigbeeBridge:
    """Zigbee через serial (CC2531/CC2652/sonoff dongle)."""
    def __init__(self, port: str, baud: int, mesh: MeshNetwork):
        self.port  = port
        self.baud  = baud
        self.mesh  = mesh
        self._ser  = None
        self._thread = None
        self._running = False

    def start(self) -> str:
        try:
            self._ser     = serial.Serial(self.port, self.baud, timeout=1)
            self._running = True
            self._thread  = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            log.info("Zigbee: %s@%d", self.port, self.baud)
            return f"✅ Zigbee запущен: {self.port}@{self.baud}"
        except Exception as e:
            return f"❌ Zigbee ошибка: {e}"

    def _read_loop(self):
        while self._running and self._ser:
            try:
                line = self._ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    self._parse(line)
            except Exception as e:
                log.error("Zigbee read: %s", e)
                time.sleep(1)

    def _parse(self, line: str):
        """Парсит входящий пакет Zigbee (JSON-формат типичных координаторов)."""
        try:
            data = json.loads(line)
            dev_id = data.get("ieeeAddr") or data.get("id", "unknown")
            self.mesh.update_device_data(dev_id, data)
            bus.publish(EventType.MESH_PACKET, {"protocol": "zigbee", "data": data}, "zigbee")
        except Exception:
            log.debug("Zigbee raw: %s", line[:80])

    def send(self, addr: str, command: str, value: Any = None) -> str:
        if not self._ser or not self._ser.is_open:
            return "❌ Zigbee порт закрыт"
        try:
            packet = json.dumps({"addr": addr, "cmd": command, "val": value}) + "\n"
            self._ser.write(packet.encode())
            return f"✅ Zigbee → {addr}: {command}={value}"
        except Exception as e:
            return f"❌ Zigbee send: {e}"

    def status(self) -> str:
        return f"{'✅ Online' if self._running and self._ser else '❌ Offline'} ({self.port})"


class LoRaBridge:
    """LoRa через serial (SX1276/SX1262/Meshtastic)."""
    def __init__(self, port: str, baud: int, mesh: MeshNetwork):
        self.port   = port
        self.baud   = baud
        self.mesh   = mesh
        self._ser   = None
        self._running = False

    def start(self) -> str:
        try:
            self._ser     = serial.Serial(self.port, self.baud, timeout=2)
            self._running = True
            # Инициализация LoRa модуля
            self._ser.write(b"AT+RST\r\n"); time.sleep(0.5)
            self._ser.write(b"AT+MODE=0\r\n"); time.sleep(0.3)  # Normal mode
            threading.Thread(target=self._read_loop, daemon=True).start()
            log.info("LoRa: %s@%d", self.port, self.baud)
            return f"✅ LoRa запущен: {self.port}@{self.baud}"
        except Exception as e:
            return f"❌ LoRa ошибка: {e}"

    def _read_loop(self):
        while self._running and self._ser:
            try:
                line = self._ser.readline().decode("utf-8", errors="ignore").strip()
                if line and not line.startswith("+OK"):
                    self._parse(line)
            except Exception:
                time.sleep(1)

    def _parse(self, line: str):
        # LoRa пакет: "+RCV=addr,len,data,rssi,snr"
        if line.startswith("+RCV="):
            try:
                parts  = line[5:].split(",")
                addr   = parts[0]
                data_s = parts[2] if len(parts) > 2 else ""
                rssi   = int(parts[3]) if len(parts) > 3 else 0
                snr    = float(parts[4]) if len(parts) > 4 else 0.0
                try:
                    payload = json.loads(data_s)
                except Exception:
                    payload = {"raw": data_s}
                payload["rssi"] = rssi
                payload["snr"]  = snr
                self.mesh.update_device_data(addr, payload)
                bus.publish(EventType.MESH_PACKET,
                            {"protocol": "lora", "addr": addr, "data": payload}, "lora")
            except Exception as e:
                log.error("LoRa parse: %s — %s", line[:60], e)

    def send(self, addr: str, command: str, value: Any = None) -> str:
        if not self._ser:
            return "❌ LoRa порт закрыт"
        try:
            payload = json.dumps({"cmd": command, "val": value})
            at_cmd  = f"AT+SEND={addr},{len(payload)},{payload}\r\n"
            self._ser.write(at_cmd.encode())
            return f"✅ LoRa → {addr}: {command}"
        except Exception as e:
            return f"❌ LoRa send: {e}"

    def status(self) -> str:
        return f"{'✅ Online' if self._running else '❌ Offline'} (LoRa {self.port})"


class WiFiMeshBridge:
    """WiFi Mesh через HTTP API (ESP-NOW координатор / Meshtastic)."""
    def __init__(self, ssid: str, mesh: MeshNetwork):
        self.ssid  = ssid
        self.mesh  = mesh
        self._running = False

    def start(self) -> str:
        self._running = True
        threading.Thread(target=self._discovery_loop, daemon=True).start()
        return f"✅ WiFi Mesh запущен. SSID: {self.ssid}"

    def _discovery_loop(self):
        import socket
        while self._running:
            try:
                # mDNS broadcast для поиска нод
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(2)
                sock.sendto(b"ARGOS_DISCOVER", ("255.255.255.255", 55770))
                try:
                    data, addr = sock.recvfrom(1024)
                    info = json.loads(data.decode("utf-8", errors="ignore"))
                    dev_id = info.get("id", addr[0])
                    self.mesh.update_device_data(dev_id, {**info, "ip": addr[0]})
                    bus.publish(EventType.MESH_NODE_FOUND,
                                {"ip": addr[0], "info": info}, "wifi_mesh")
                except Exception:
                    pass
                sock.close()
            except Exception:
                pass
            time.sleep(15)

    def send(self, addr: str, command: str, value: Any = None) -> str:
        import urllib.request
        try:
            payload = json.dumps({"cmd": command, "val": value}).encode()
            req = urllib.request.Request(
                f"http://{addr}/api/cmd",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                return f"✅ WiFi → {addr}: {command} → {r.read().decode()[:50]}"
        except Exception as e:
            return f"❌ WiFi send {addr}: {e}"

    def status(self) -> str:
        return f"{'✅ Online' if self._running else '❌ Offline'} (WiFi Mesh)"


class GatewayFlasher:
    """Прошивка gateway устройств (ESP32/Arduino) из Аргоса."""
    def flash(self, port: str, fw_path: str) -> str:
        ext = os.path.splitext(fw_path)[1].lower()
        log.info("Прошивка: %s → %s", fw_path, port)
        if ext == ".bin":
            return self._flash_esp(port, fw_path)
        elif ext == ".hex":
            return self._flash_avr(port, fw_path)
        return f"❌ Неизвестный формат прошивки: {ext}"

    def _flash_esp(self, port: str, fw_path: str) -> str:
        """ESP32/ESP8266 через esptool."""
        import subprocess
        try:
            result = subprocess.run(
                ["esptool.py", "--port", port, "--baud", "921600",
                 "write_flash", "-z", "0x0", fw_path],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                return f"✅ ESP прошит: {os.path.basename(fw_path)}"
            return f"❌ esptool: {result.stderr[:200]}"
        except FileNotFoundError:
            return "❌ esptool не найден: pip install esptool"
        except Exception as e:
            return f"❌ Прошивка: {e}"

    def _flash_avr(self, port: str, fw_path: str) -> str:
        """Arduino/AVR через avrdude."""
        import subprocess
        try:
            result = subprocess.run(
                ["avrdude", "-p", "m328p", "-c", "arduino",
                 "-P", port, "-b", "115200",
                 "-U", f"flash:w:{fw_path}:i"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                return f"✅ AVR прошит: {os.path.basename(fw_path)}"
            return f"❌ avrdude: {result.stderr[:200]}"
        except FileNotFoundError:
            return "❌ avrdude не найден: sudo apt install avrdude"
        except Exception as e:
            return f"❌ Прошивка: {e}"
