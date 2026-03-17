"""
smart_systems.py — Аргос как оператор умных систем
  Умный дом, теплица, гараж, погреб, инкубатор, аквариум, террариум.
  Автоматические правила, оповещения, управление через mesh-сеть.
"""
import json
import os
import time
import threading
import ast
from src.argos_logger import get_logger
from src.connectivity.event_bus import bus, EventType

log = get_logger("argos.smart")
SYSTEMS_DB = "config/smart_systems.json"


def _safe_eval_condition(expr: str, variables: dict) -> bool:
    """Безопасная оценка простых условий правил без доступа к builtins."""
    tree = ast.parse(expr, mode="eval")
    allowed_nodes = (
        ast.Expression,
        ast.BoolOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
    )

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"Недопустимый элемент в условии: {type(node).__name__}")

    return bool(eval(compile(tree, "<smart-rule>", "eval"), {"__builtins__": {}}, variables))


# ── ПАРАМЕТРЫ КАЖДОЙ СИСТЕМЫ ──────────────────────────────
SYSTEM_PROFILES = {
    "home": {
        "name": "Умный дом",
        "icon": "🏠",
        "sensors": ["temp", "humidity", "co2", "motion", "door", "smoke"],
        "actuators": ["light", "thermostat", "lock", "alarm", "fan"],
        "rules": [
            {"if": "temp > 28", "then": "fan:on",   "msg": "Жара — включил вентилятор"},
            {"if": "temp < 18", "then": "heat:on",   "msg": "Холодно — включил обогрев"},
            {"if": "smoke > 5", "then": "alarm:on",  "msg": "⚠️ ДЫМОВОЙ ДАТЧИК СРАБОТАЛ"},
            {"if": "co2 > 1200","then": "fan:on",    "msg": "CO2 высокий — вентиляция"},
            {"if": "motion == 1 and time > '23:00'", "then": "light:on", "msg": "Движение ночью"},
        ]
    },
    "greenhouse": {
        "name": "Умная теплица",
        "icon": "🌱",
        "sensors": ["temp", "humidity", "soil_moisture", "light_lux", "co2", "ph"],
        "actuators": ["irrigation", "heating", "ventilation", "lamp", "shade"],
        "rules": [
            {"if": "soil_moisture < 30", "then": "irrigation:on",  "msg": "Полив — почва сухая"},
            {"if": "soil_moisture > 80", "then": "irrigation:off", "msg": "Полив остановлен"},
            {"if": "temp > 35",          "then": "ventilation:on", "msg": "Жара в теплице"},
            {"if": "temp < 15",          "then": "heating:on",     "msg": "Холод в теплице"},
            {"if": "light_lux < 500",    "then": "lamp:on",        "msg": "Досвечивание включено"},
            {"if": "humidity < 50",      "then": "irrigation:on",  "msg": "Низкая влажность"},
        ]
    },
    "garage": {
        "name": "Умный гараж",
        "icon": "🚗",
        "sensors": ["gas", "motion", "door_open", "temp", "flood"],
        "actuators": ["gate", "light", "alarm", "fan", "heater"],
        "rules": [
            {"if": "gas > 400",    "then": "fan:on",   "msg": "⚠️ Газ в гараже — вентиляция"},
            {"if": "flood > 0",    "then": "alarm:on", "msg": "⚠️ ВОДА В ГАРАЖЕ"},
            {"if": "temp < 5",     "then": "heater:on","msg": "Мороз — обогрев гаража"},
            {"if": "motion == 1",  "then": "light:on", "msg": "Движение — свет включён"},
        ]
    },
    "cellar": {
        "name": "Умный погреб",
        "icon": "🏚️",
        "sensors": ["temp", "humidity", "flood", "co2"],
        "actuators": ["fan", "alarm", "pump", "heater"],
        "rules": [
            {"if": "temp > 10",     "then": "fan:on",  "msg": "Тепло в погребе — вентиляция"},
            {"if": "temp < 2",      "then": "heater:on","msg": "Мороз в погребе — обогрев"},
            {"if": "humidity > 90", "then": "fan:on",  "msg": "Высокая влажность в погребе"},
            {"if": "flood > 0",     "then": "pump:on", "msg": "⚠️ ВОДА В ПОГРЕБЕ — насос"},
        ]
    },
    "incubator": {
        "name": "Инкубатор",
        "icon": "🥚",
        "sensors": ["temp", "humidity", "co2", "turn_count"],
        "actuators": ["heater", "fan", "turner", "humidifier"],
        "rules": [
            {"if": "temp < 37.5", "then": "heater:on",     "msg": "Температура низкая — нагрев"},
            {"if": "temp > 38.0", "then": "heater:off",    "msg": "Температура норма — нагрев выкл"},
            {"if": "humidity < 50","then": "humidifier:on","msg": "Влажность низкая — увлажнение"},
            {"if": "humidity > 70","then": "humidifier:off","msg":"Влажность норма"},
            {"if": "turn_count < 3", "then": "turner:rotate","msg": "Переворот яиц"},
        ]
    },
    "aquarium": {
        "name": "Аквариум",
        "icon": "🐠",
        "sensors": ["temp", "ph", "tds", "o2", "water_level", "ammonia"],
        "actuators": ["heater", "pump", "filter", "lamp", "co2_inject", "feeder"],
        "rules": [
            {"if": "temp < 24",   "then": "heater:on",     "msg": "Вода холодная — нагрев"},
            {"if": "temp > 28",   "then": "heater:off",    "msg": "Вода тёплая — нагрев выкл"},
            {"if": "ph < 6.5",    "then": "co2_inject:off","msg": "pH низкий — CO2 выкл"},
            {"if": "ph > 7.8",    "then": "co2_inject:on", "msg": "pH высокий — CO2 вкл"},
            {"if": "o2 < 6",      "then": "pump:high",     "msg": "O2 низкий — насос на максимум"},
            {"if": "ammonia > 0.5","then": "filter:on",    "msg": "⚠️ Аммиак — фильтр на максимум"},
            {"if": "water_level < 80","then": "alarm:on",  "msg": "⚠️ Уровень воды низкий"},
        ]
    },
    "terrarium": {
        "name": "Террариум",
        "icon": "🦎",
        "sensors": ["temp_hot", "temp_cool", "humidity", "uvi", "motion"],
        "actuators": ["lamp_uv", "lamp_heat", "mister", "fan"],
        "rules": [
            {"if": "temp_hot < 30",  "then": "lamp_heat:on", "msg": "Холодно — нагревательная лампа"},
            {"if": "temp_hot > 36",  "then": "lamp_heat:off","msg": "Норм — лампа выкл"},
            {"if": "humidity < 60",  "then": "mister:on",    "msg": "Влажность низкая — туман"},
            {"if": "uvi < 2.0",      "then": "lamp_uv:on",   "msg": "УФ низкий — УФ лампа"},
        ]
    },
}


class SmartSystem:
    """Один тип умной системы с устройствами и правилами."""

    def __init__(self, sys_type: str, instance_id: str = "main"):
        profile          = SYSTEM_PROFILES.get(sys_type, {})
        self.type        = sys_type
        self.id          = instance_id
        self.name        = profile.get("name", sys_type)
        self.icon        = profile.get("icon", "⚙️")
        self.sensors     = {}   # {sensor_name: value}
        self.actuators   = {}   # {actuator_name: state}
        self.rules       = profile.get("rules", [])
        self.custom_rules= []
        self.history     = []   # [(ts, event)]
        self._callbacks  = []   # вызываются при срабатывании правила

    def update_sensor(self, sensor: str, value):
        self.sensors[sensor] = value
        log.debug("%s.%s → %s = %s", self.type, self.id, sensor, value)
        bus.publish(EventType.SENSOR_UPDATE,
                    {"system": self.id, "sensor": sensor, "value": value}, "smart")
        self._check_rules()

    def set_actuator(self, actuator: str, state: str):
        old = self.actuators.get(actuator)
        self.actuators[actuator] = state
        if old != state:
            event = f"{actuator}:{state}"
            self.history.append((time.time(), event))
            bus.publish(EventType.DEVICE_CMD,
                        {"system": self.id, "actuator": actuator, "state": state}, "smart")
            log.info("SMART %s → %s = %s", self.id, actuator, state)

    def add_rule(self, condition: str, action: str, msg: str = "") -> str:
        self.custom_rules.append({"if": condition, "then": action, "msg": msg or action})
        return f"✅ Правило добавлено: если {condition} → {action}"

    def _check_rules(self):
        for rule in (self.rules + self.custom_rules):
            try:
                cond = rule["if"]
                # Заменяем имена сенсоров на значения
                expr = cond
                for s, v in self.sensors.items():
                    val = f'"{v}"' if isinstance(v, str) else str(v)
                    expr = expr.replace(s, val)
                if _safe_eval_condition(expr, {"time": time.strftime("%H:%M")}):
                    action  = rule["then"]
                    msg     = rule.get("msg", action)
                    act, st = action.split(":") if ":" in action else (action, "on")
                    self.set_actuator(act, st)
                    bus.publish(EventType.SMART_RULE_FIRE,
                                {"rule": cond, "action": action, "msg": msg}, "smart")
                    for cb in self._callbacks:
                        try:
                            cb(msg)
                        except Exception as e:
                            log.warning("Smart callback error (%s): %s", self.id, e)
            except Exception as e:
                log.warning("Правило '%s' в системе '%s' пропущено: %s", rule.get("if", "?"), self.id, e)

    def status(self) -> str:
        lines = [f"{self.icon} {self.name} [{self.id}]:"]
        if self.sensors:
            lines.append("  Сенсоры:")
            for s, v in self.sensors.items():
                lines.append(f"    {s:20s} = {v}")
        if self.actuators:
            lines.append("  Актуаторы:")
            for a, s in self.actuators.items():
                icon = "🟢" if s in ("on","high","open","rotate") else "🔴"
                lines.append(f"    {icon} {a:20s} = {s}")
        if self.history:
            lines.append(f"  Последние события ({min(3,len(self.history))}):")
            for ts, ev in self.history[-3:]:
                lines.append(f"    {time.strftime('%H:%M:%S', time.localtime(ts))} {ev}")
        return "\n".join(lines)


class SmartSystemsManager:
    """Управляет всеми умными системами в доме Аргоса."""

    def __init__(self, on_alert=None):
        self.systems: dict[str, SmartSystem] = {}
        self._on_alert = on_alert
        self._load()
        # Подписываемся на события сенсоров
        bus.subscribe(EventType.SENSOR_UPDATE, self._on_sensor_event)
        bus.subscribe(EventType.SMART_ALERT, self._on_smart_alert)

    def _load(self):
        if os.path.exists(SYSTEMS_DB):
            try:
                data = json.load(open(SYSTEMS_DB, encoding="utf-8"))
                for sys_id, sdata in data.items():
                    sys_type = sdata.get("type", sys_id)
                    ss = SmartSystem(sys_type, sys_id)
                    ss.sensors   = sdata.get("sensors", {})
                    ss.actuators = sdata.get("actuators", {})
                    ss.custom_rules = sdata.get("custom_rules", [])
                    if self._on_alert:
                        ss._callbacks.append(self._on_alert)
                    self.systems[sys_id] = ss
                log.info("SmartSystems: загружено %d систем", len(self.systems))
            except Exception as e:
                log.error("SmartSystems load: %s", e)

    def _save(self):
        os.makedirs("config", exist_ok=True)
        data = {
            sid: {
                "type": ss.type, "sensors": ss.sensors,
                "actuators": ss.actuators, "custom_rules": ss.custom_rules,
            }
            for sid, ss in self.systems.items()
        }
        json.dump(data, open(SYSTEMS_DB, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)

    def _on_sensor_event(self, ev):
        payload = ev.payload or {}
        sys_id  = payload.get("system")
        if sys_id and sys_id in self.systems:
            sensor = payload.get("sensor")
            value  = payload.get("value")
            if sensor and value is not None:
                self.systems[sys_id].update_sensor(sensor, value)

    def _on_smart_alert(self, ev):
        if self._on_alert and ev.payload:
            msg = ev.payload.get("msg", str(ev.payload))
            self._on_alert(f"🏠 SMART ALERT: {msg}")

    def add_system(self, sys_type: str, instance_id: str = None) -> str:
        if sys_type not in SYSTEM_PROFILES:
            avail = ", ".join(SYSTEM_PROFILES.keys())
            return f"❌ Тип не найден. Доступные: {avail}"
        sid = instance_id or sys_type
        ss  = SmartSystem(sys_type, sid)
        if self._on_alert:
            ss._callbacks.append(self._on_alert)
        self.systems[sid] = ss
        self._save()
        profile = SYSTEM_PROFILES[sys_type]
        log.info("Добавлена система: %s", sid)
        return (f"✅ {profile['icon']} {profile['name']} [{sid}] добавлена!\n"
                f"   Сенсоры: {', '.join(profile['sensors'])}\n"
                f"   Актуаторы: {', '.join(profile['actuators'])}\n"
                f"   Правил: {len(profile['rules'])}")

    def update(self, sys_id: str, sensor: str, value) -> str:
        if sys_id not in self.systems:
            return f"❌ Система не найдена: {sys_id}"
        try:
            value = float(value)
        except Exception:
            pass
        self.systems[sys_id].update_sensor(sensor, value)
        self._save()
        return f"✅ {sys_id}.{sensor} = {value}"

    def command(self, sys_id: str, actuator: str, state: str) -> str:
        if sys_id not in self.systems:
            return f"❌ Система: {sys_id}"
        self.systems[sys_id].set_actuator(actuator, state)
        self._save()
        return f"✅ {sys_id} → {actuator} = {state}"

    def full_status(self) -> str:
        if not self.systems:
            avail = ", ".join(SYSTEM_PROFILES.keys())
            return (f"📭 Умных систем нет.\n"
                    f"  Добавь: аргос, добавь систему [тип] [id]\n"
                    f"  Типы: {avail}")
        lines = ["🏠 УМНЫЕ СИСТЕМЫ АРГОСА:"]
        for sid, ss in self.systems.items():
            lines.append(f"\n{ss.status()}")
        return "\n".join(lines)

    def available_types(self) -> str:
        lines = ["🏠 ДОСТУПНЫЕ УМНЫЕ СИСТЕМЫ:"]
        for sys_type, profile in SYSTEM_PROFILES.items():
            lines.append(f"  {profile['icon']} {sys_type:15s} — {profile['name']}")
            lines.append(f"       Сенсоры: {', '.join(profile['sensors'][:4])}...")
        return "\n".join(lines)
