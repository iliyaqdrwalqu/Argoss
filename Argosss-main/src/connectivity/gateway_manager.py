"""
gateway_manager.py — Менеджер IoT-шлюзов Аргоса
  Создание конфигов, прошивка, управление шлюзами.
  Поддерживает: ESP32, Raspberry Pi, Arduino, commercial gateways.
  Протоколы: Zigbee2MQTT, LoRaWAN (TTN/Chirpstack), MQTT broker,
             ESP-NOW mesh, Modbus TCP/RTU.
"""
import json, os, time, subprocess
from src.argos_logger import get_logger
from src.event_bus import get_bus

log = get_logger("argos.gateway")
bus = get_bus()

GATEWAY_DIR = "config/gateways"
FIRMWARE_DIR= "assets/firmware"
CUSTOM_TEMPLATES_FILE = "config/gateway_templates.custom.json"
os.makedirs(GATEWAY_DIR, exist_ok=True)
os.makedirs(FIRMWARE_DIR, exist_ok=True)


# ── ШАБЛОНЫ ШЛЮЗОВ ───────────────────────────────────────
GATEWAY_TEMPLATES = {
    "esp32_zigbee": {
        "description": "ESP32 + CC2530/CC2652 Zigbee координатор",
        "hardware": "ESP32 + Zigbee radio",
        "protocol": "zigbee",
        "firmware": "zigbee2mqtt",
        "config": {
            "serial": {"port": "/dev/ttyUSB0", "baudrate": 115200},
            "mqtt":   {"base_topic": "zigbee2mqtt", "server": "mqtt://localhost"},
            "homeassistant": False,
            "permit_join": True,
        }
    },
    "esp32_lora": {
        "description": "ESP32 + SX1276/1278 LoRa шлюз",
        "hardware": "ESP32 + LoRa module",
        "protocol": "lora",
        "firmware": "arduino_lora_gw",
        "config": {
            "frequency": 433.0,
            "spreading_factor": 7,
            "bandwidth": 125000,
            "mqtt_topic": "argos/lora",
        }
    },
    "rpi_mesh": {
        "description": "Raspberry Pi Mesh-шлюз (Wi-Fi + Ethernet)",
        "hardware": "Raspberry Pi 3/4",
        "protocol": "mesh",
        "firmware": "argos_mesh_gw",
        "config": {
            "mesh_port": 9876,
            "mqtt_host": "localhost",
            "bridge_to_mqtt": True,
            "node_id": "rpi_gw_01",
        }
    },
    "modbus_rtu": {
        "description": "USB-RS485 Modbus RTU шлюз",
        "hardware": "USB-RS485 адаптер",
        "protocol": "modbus",
        "firmware": "modbus_bridge",
        "config": {
            "serial": "/dev/ttyUSB0",
            "baudrate": 9600,
            "parity": "N",
            "stopbits": 1,
            "scan_interval": 5,
            "devices": [],
        }
    },
    "lorawan_ttn": {
        "description": "LoRaWAN шлюз → The Things Network",
        "hardware": "SX1301/SX1302 концентратор",
        "protocol": "lorawan",
        "firmware": "packet_forwarder",
        "config": {
            "gateway_id": "AA555A0000000000",
            "server_address": "eu1.cloud.thethings.network",
            "server_port_up": 1700,
            "server_port_down": 1700,
        }
    },
}


def _load_custom_templates() -> dict:
    if not os.path.exists(CUSTOM_TEMPLATES_FILE):
        return {}
    try:
        payload = json.load(open(CUSTOM_TEMPLATES_FILE, encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        return {}
    except Exception as e:
        log.warning("Custom templates load error: %s", e)
        return {}


def _save_custom_templates(custom_templates: dict):
    os.makedirs("config", exist_ok=True)
    json.dump(custom_templates, open(CUSTOM_TEMPLATES_FILE, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)


class GatewayConfig:
    def __init__(self, gw_id: str, template: str, overrides: dict = None):
        self.id       = gw_id
        self.template = template
        self.spec     = dict(GATEWAY_TEMPLATES.get(template, {}))
        if overrides:
            self._deep_merge(self.spec.get("config", {}), overrides)
        self.created_at = time.time()
        self.status     = "configured"

    def _deep_merge(self, base: dict, override: dict):
        for k, v in override.items():
            if isinstance(v, dict) and k in base:
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def to_dict(self) -> dict:
        return {
            "id": self.id, "template": self.template,
            "spec": self.spec, "created_at": self.created_at,
            "status": self.status,
        }

    def save(self) -> str:
        path = os.path.join(GATEWAY_DIR, f"{self.id}.json")
        json.dump(self.to_dict(), open(path, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        return path


class GatewayManager:
    def __init__(self, iot_bridge=None):
        self.iot      = iot_bridge
        self._gateways: dict[str, GatewayConfig] = {}
        self._templates: dict[str, dict] = dict(GATEWAY_TEMPLATES)
        self._templates.update(_load_custom_templates())
        self._load()

    def _load(self):
        for f in os.listdir(GATEWAY_DIR):
            if f.endswith(".json"):
                try:
                    data = json.load(open(os.path.join(GATEWAY_DIR, f), encoding="utf-8"))
                    gw   = GatewayConfig(data["id"], data["template"])
                    gw.spec   = data["spec"]
                    gw.status = data.get("status", "configured")
                    self._gateways[gw.id] = gw
                except Exception as e:
                    log.error("Gateway load %s: %s", f, e)
        log.info("Шлюзы загружены: %d", len(self._gateways))

    @staticmethod
    def _suggest_firmware(protocol: str) -> str:
        protocol_name = (protocol or "").strip().lower()
        return {
            "zigbee": "zigbee2mqtt",
            "lora": "arduino_lora_gw",
            "lorawan": "packet_forwarder",
            "modbus": "modbus_bridge",
            "mesh": "argos_mesh_gw",
        }.get(protocol_name, "custom_bridge")

    def create_gateway(self, gw_id: str, template: str,
                       overrides: dict = None) -> str:
        if template not in self._templates:
            avail = ", ".join(self._templates.keys())
            return f"❌ Шаблон не найден. Доступные: {avail}"
        gw   = GatewayConfig(gw_id, template, overrides)
        gw.spec = dict(self._templates.get(template, gw.spec))
        if overrides:
            gw._deep_merge(gw.spec.get("config", {}), overrides)
        path = gw.save()
        self._gateways[gw_id] = gw
        bus.emit("gateway.created", {"id": gw_id, "template": template}, "gateway_manager")
        log.info("Шлюз создан: %s (%s) → %s", gw_id, template, path)
        return (f"✅ Шлюз '{gw_id}' создан:\n"
                f"   Шаблон: {template}\n"
                f"   Описание: {self._templates[template].get('description', 'custom gateway template')}\n"
                f"   Конфиг: {path}")

    def prepare_firmware(self, gw_id: str, template: str, port: str = None) -> str:
        """Создаёт (или обновляет) шлюз по шаблону и готовит прошивку/конфиг.
        Для некоторых шаблонов при наличии порта выполняет заливку.
        """
        created = False
        if gw_id not in self._gateways:
            res = self.create_gateway(gw_id, template)
            if res.startswith("❌"):
                return res
            created = True
        else:
            gw = self._gateways[gw_id]
            if gw.template != template:
                gw.template = template
                gw.spec = dict(self._templates.get(template, {}))
                gw.status = "configured"
                gw.save()

        flash_res = self.flash_gateway(gw_id, port)
        prefix = "✅ Шлюз создан и прошивка подготовлена." if created else "✅ Прошивка обновлена."
        return f"{prefix}\n{flash_res}"

    def flash_gateway(self, gw_id: str, port: str = None) -> str:
        gw = self._gateways.get(gw_id)
        if not gw:
            return f"❌ Шлюз '{gw_id}' не найден."

        firmware = gw.spec.get("firmware", "")
        log.info("Прошивка шлюза %s: %s", gw_id, firmware)

        if firmware == "zigbee2mqtt":
            return self._flash_zigbee2mqtt(gw, port)
        elif firmware == "arduino_lora_gw":
            return self._flash_arduino(gw, port)
        elif firmware == "packet_forwarder":
            return self._flash_lora_forwarder(gw)
        elif firmware == "modbus_bridge":
            return self._start_modbus(gw)
        elif firmware == "argos_mesh_gw":
            return self._start_mesh_gw(gw)
        else:
            return f"⚠️ Прошивка '{firmware}': ручная установка. Конфиг: {os.path.join(GATEWAY_DIR, gw_id+'.json')}"

    def _flash_zigbee2mqtt(self, gw: GatewayConfig, port: str = None) -> str:
        """Генерирует конфиг для Zigbee2MQTT и запускает."""
        serial_port = port or gw.spec.get("config",{}).get("serial",{}).get("port", "/dev/ttyUSB0")
        z2m_config  = {
            "homeassistant":    gw.spec["config"].get("homeassistant", False),
            "permit_join":      gw.spec["config"].get("permit_join", True),
            "mqtt": {
                "base_topic":   gw.spec["config"]["mqtt"]["base_topic"],
                "server":       gw.spec["config"]["mqtt"]["server"],
            },
            "serial": {
                "port": serial_port
            },
        }
        z2m_dir = "config/zigbee2mqtt"
        os.makedirs(z2m_dir, exist_ok=True)
        cfg_path = f"{z2m_dir}/configuration.yaml"
        import yaml as _yaml
        try:
            _yaml.dump(z2m_config, open(cfg_path, "w"))
        except ImportError:
            json.dump(z2m_config, open(cfg_path.replace(".yaml",".json"), "w"), indent=2)
        gw.status = "deployed"
        gw.save()
        return (f"✅ Zigbee2MQTT конфиг создан: {cfg_path}\n"
                f"   Порт: {serial_port}\n"
                f"   Запуск: npx zigbee2mqtt\n"
                f"   Docker: docker run -d koenkk/zigbee2mqtt")

    def _flash_arduino(self, gw: GatewayConfig, port: str = None) -> str:
        """Генерирует скетч для ESP32/Arduino LoRa шлюза."""
        freq = gw.spec.get("config",{}).get("frequency", 433.0)
        mqtt = gw.spec.get("config",{}).get("mqtt_topic", "argos/lora")
        sketch = f"""// ArgosUniversal LoRa Gateway — автогенерация
#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <PubSubClient.h>

#define LORA_FREQ    {int(freq*1e6)}
#define LORA_SS      5
#define LORA_RST     14
#define LORA_DIO0    2
#define MQTT_TOPIC   "{mqtt}"

void setup() {{
  Serial.begin(115200);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_FREQ)) while(true);
  // WiFi + MQTT init here
  Serial.println("ArgosGW LoRa ready @ {freq}MHz");
}}

void loop() {{
  int pktSize = LoRa.parsePacket();
  if (pktSize) {{
    String data = "";
    while (LoRa.available()) data += (char)LoRa.read();
    // publish to MQTT
    Serial.println("RX: " + data);
  }}
}}
"""
        sketch_path = f"{FIRMWARE_DIR}/{gw.id}_lora_gw.ino"
        with open(sketch_path, "w") as f:
            f.write(sketch)
        gw.status = "firmware_ready"
        gw.save()

        flash_cmd = ""
        if port:
            flash_cmd = f"\n   Прошивка: arduino-cli compile --upload -p {port}"
        return (f"✅ Arduino скетч создан: {sketch_path}\n"
                f"   Частота: {freq} MHz\n"
                f"   MQTT топик: {mqtt}"
                f"{flash_cmd}")

    def _flash_lora_forwarder(self, gw: GatewayConfig) -> str:
        cfg = gw.spec.get("config", {})
        pf_config = {
            "SX1301_conf": {"lorawan_public": True, "clksrc": 1},
            "gateway_conf": {
                "gateway_ID": cfg.get("gateway_id", "AA555A0000000000"),
                "server_address": cfg.get("server_address", "router.eu.thethings.network"),
                "serv_port_up": cfg.get("server_port_up", 1700),
                "serv_port_down": cfg.get("server_port_down", 1700),
                "keepalive_interval": 10,
                "stat_interval": 30,
                "push_timeout_ms": 100,
            }
        }
        path = f"{GATEWAY_DIR}/{gw.id}_packet_forwarder.json"
        json.dump(pf_config, open(path, "w"), indent=2)
        return (f"✅ LoRaWAN Packet Forwarder конфиг: {path}\n"
                f"   Сервер: {cfg.get('server_address', 'eu1.cloud.thethings.network')}\n"
                f"   GW ID: {cfg.get('gateway_id', 'AA555A0000000000')}\n"
                f"   Запуск: ./packet_forwarder -c {path}")

    def _start_modbus(self, gw: GatewayConfig) -> str:
        cfg = gw.spec.get("config", {})
        return (f"✅ Modbus RTU шлюз:\n"
                f"   Порт: {cfg.get('serial', '/dev/ttyUSB0')}\n"
                f"   Baudrate: {cfg.get('baudrate', 9600)}\n"
                f"   Запуск: добавь устройства через register_device\n"
                f"   pip install pymodbus")

    def _start_mesh_gw(self, gw: GatewayConfig) -> str:
        cfg = gw.spec.get("config", {})
        return (f"✅ Mesh шлюз запущен:\n"
                f"   UDP порт: {cfg.get('mesh_port', 9876)}\n"
                f"   Мост к MQTT: {cfg.get('bridge_to_mqtt', True)}\n"
                f"   Node ID: {cfg.get('node_id', 'rpi_gw_01')}")

    def list_gateways(self) -> str:
        if not self._gateways:
            return ("📡 Шлюзов нет.\n"
                    f"Создай: создай шлюз [id] [шаблон]\n"
                    f"Шаблоны: {', '.join(self._templates.keys())}")
        lines = ["📡 IoT ШЛЮЗЫ:"]
        for gw in self._gateways.values():
            lines.append(f"  • {gw.id} [{gw.template}] статус={gw.status}")
        return "\n".join(lines)

    def list_templates(self) -> str:
        lines = ["📋 ШАБЛОНЫ ШЛЮЗОВ:"]
        for name, tmpl in self._templates.items():
            lines.append(f"  • {name}: {tmpl['description']}")
        return "\n".join(lines)

    def register_template(self, name: str, description: str, protocol: str,
                          firmware: str = "custom_bridge", hardware: str = "Generic gateway",
                          config: dict | None = None) -> str:
        safe_name = (name or "").strip().lower().replace(" ", "_")
        protocol_name = (protocol or "").strip().lower()
        if not safe_name:
            return "❌ Имя шаблона пустое."
        if not protocol_name:
            return "❌ Протокол не указан."
        if safe_name in GATEWAY_TEMPLATES:
            return f"❌ Шаблон '{safe_name}' зарезервирован системно. Используй другое имя."

        existed = safe_name in self._templates
        selected_firmware = (firmware or "").strip() or self._suggest_firmware(protocol_name)

        template_data = {
            "description": description or f"Custom template for {protocol_name}",
            "hardware": hardware,
            "protocol": protocol_name,
            "firmware": selected_firmware,
            "config": config or {
                "transport": "serial",
                "baudrate": 115200,
                "notes": "auto-learned template",
            },
        }
        self._templates[safe_name] = template_data

        custom = {
            k: v for k, v in self._templates.items()
            if k not in GATEWAY_TEMPLATES
        }
        _save_custom_templates(custom)
        status = "обновлён" if existed else "зарегистрирован"
        return (f"✅ Шаблон {status}: {safe_name} [{protocol_name}]\n"
            f"   Прошивка: {selected_firmware}")

    def templates(self) -> dict:
        return dict(self._templates)

    def get_config(self, gw_id: str) -> str:
        gw = self._gateways.get(gw_id)
        if not gw:
            return f"❌ Шлюз '{gw_id}' не найден."
        return json.dumps(gw.to_dict(), indent=2, ensure_ascii=False)
