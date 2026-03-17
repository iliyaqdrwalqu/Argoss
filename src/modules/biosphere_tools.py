"""
biosphere_tools.py — Датчики и актуаторы биосферы.
Temp / Humidity / Light / CO2 / pH / EC через I2C, UART, GPIO.
"""
import os
import time
import threading
from typing import Optional, Dict
from dataclasses import dataclass, field, asdict
from src.argos_logger import get_logger

log = get_logger("argos.biosphere")

# ── Graceful hardware imports ────────────────────────────────
try:
    import smbus2
    SMBUS_OK = True
except ImportError:
    smbus2 = None; SMBUS_OK = False

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO_OK = True
except Exception:
    GPIO = None; GPIO_OK = False

try:
    import serial
    SERIAL_OK = True
except ImportError:
    serial = None; SERIAL_OK = False


# ── I2C адреса стандартных датчиков ──────────────────────────
SENSOR_ADDR = {
    "SHT31":  0x44,  # Temp+Humidity
    "BH1750": 0x23,  # Light lux
    "SCD41":  0x62,  # CO2+Temp+Humidity
    "BMP280": 0x76,  # Pressure+Temp
    "AHT20":  0x38,  # Temp+Humidity
}


@dataclass
class SensorReading:
    sensor_id: str
    sensor_type: str = ""
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    light_lux: Optional[float] = None
    co2_ppm: Optional[float] = None
    pressure_hpa: Optional[float] = None
    ph: Optional[float] = None
    ec_us: Optional[float] = None
    raw: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    simulated: bool = False

    def to_dict(self): return asdict(self)


@dataclass
class ActuatorState:
    actuator_id: str
    type: str = "relay"
    pin: int = 0
    state: bool = False
    last_changed: float = field(default_factory=time.time)

    def to_dict(self): return asdict(self)


class BiosphereSensorHub:
    """Хаб датчиков биосферы (I2C + UART + симуляция)."""

    def __init__(self, bus_num: int = 1):
        self._bus = None
        self._bus_num = bus_num
        self._readings: Dict[str, SensorReading] = {}
        self._actuators: Dict[str, ActuatorState] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_bus()

    def _init_bus(self) -> None:
        if SMBUS_OK:
            try:
                self._bus = smbus2.SMBus(self._bus_num)
                log.info("Biosphere: I2C bus %d OK", self._bus_num)
            except Exception as e:
                log.warning("Biosphere: I2C bus %d error: %s", self._bus_num, e)

    def start_polling(self, interval: float = 5.0) -> str:
        if self._running:
            return "ℹ️ Biosphere polling уже запущен"
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop,
                                        args=(interval,), daemon=True)
        self._thread.start()
        return f"✅ Biosphere polling запущен (каждые {interval}с)"

    def stop_polling(self) -> str:
        self._running = False
        return "✅ Biosphere polling остановлен"

    def _poll_loop(self, interval: float):
        while self._running:
            self.read_all()
            time.sleep(interval)

    def read_all(self) -> dict:
        """Читает все зарегистрированные датчики."""
        results = {}
        for sid, r in list(self._readings.items()):
            updated = self._read_sensor(sid)
            if updated:
                self._readings[sid] = updated
                results[sid] = updated.to_dict()
        if not results:
            # Симуляция для разработки
            results = self._simulate_readings()
        return results

    def _read_sensor(self, sensor_id: str) -> Optional[SensorReading]:
        r = self._readings.get(sensor_id)
        if not r or not self._bus:
            return None
        stype = r.sensor_type.upper()
        try:
            if stype == "SHT31":
                return self._read_sht31(sensor_id)
            elif stype == "BH1750":
                return self._read_bh1750(sensor_id)
            elif stype == "BMP280":
                return self._read_bmp280(sensor_id)
        except Exception as e:
            log.debug("Biosphere read %s: %s", sensor_id, e)
        return None

    def _read_sht31(self, sid: str) -> SensorReading:
        addr = SENSOR_ADDR["SHT31"]
        self._bus.write_i2c_block_data(addr, 0x24, [0x00])
        time.sleep(0.02)
        data = self._bus.read_i2c_block_data(addr, 0x00, 6)
        raw_temp = data[0] * 256 + data[1]
        raw_hum  = data[3] * 256 + data[4]
        temp = -45 + (175 * raw_temp / 65535.0)
        hum  = 100 * raw_hum / 65535.0
        return SensorReading(sensor_id=sid, sensor_type="SHT31",
                             temperature=round(temp, 2), humidity=round(hum, 2))

    def _read_bh1750(self, sid: str) -> SensorReading:
        addr = SENSOR_ADDR["BH1750"]
        self._bus.write_byte(addr, 0x10)
        time.sleep(0.18)
        data = self._bus.read_i2c_block_data(addr, 0x00, 2)
        lux = (data[0] * 256 + data[1]) / 1.2
        return SensorReading(sensor_id=sid, sensor_type="BH1750",
                             light_lux=round(lux, 1))

    def _read_bmp280(self, sid: str) -> SensorReading:
        # Упрощённое чтение без компенсации
        addr = SENSOR_ADDR["BMP280"]
        data = self._bus.read_i2c_block_data(addr, 0xF7, 6)
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        # Грубая приближённая конвертация
        temp = (adc_t / 5242880.0) * 25.0
        press = (adc_p / 262144.0) * 1013.25
        return SensorReading(sensor_id=sid, sensor_type="BMP280",
                             temperature=round(temp, 1), pressure_hpa=round(press, 1))

    def _simulate_readings(self) -> dict:
        """Симуляция показаний для разработки без железа."""
        import random
        return {
            "sim_temp_hum": SensorReading(
                sensor_id="sim_temp_hum", sensor_type="SHT31_sim",
                temperature=round(22.0 + random.uniform(-1, 1), 1),
                humidity=round(55.0 + random.uniform(-5, 5), 1),
                simulated=True
            ).to_dict(),
            "sim_light": SensorReading(
                sensor_id="sim_light", sensor_type="BH1750_sim",
                light_lux=round(1200 + random.uniform(-100, 100), 1),
                simulated=True
            ).to_dict(),
        }

    def register_sensor(self, sensor_id: str, sensor_type: str) -> str:
        self._readings[sensor_id] = SensorReading(
            sensor_id=sensor_id, sensor_type=sensor_type)
        return f"✅ Датчик зарегистрирован: {sensor_id} ({sensor_type})"

    def register_actuator(self, act_id: str, pin: int,
                          act_type: str = "relay") -> str:
        self._actuators[act_id] = ActuatorState(
            actuator_id=act_id, type=act_type, pin=pin)
        if GPIO_OK:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        return f"✅ Актуатор зарегистрирован: {act_id} pin={pin}"

    def set_actuator(self, act_id: str, state: bool) -> str:
        act = self._actuators.get(act_id)
        if not act:
            return f"❌ Актуатор не найден: {act_id}"
        act.state = state
        act.last_changed = time.time()
        if GPIO_OK:
            GPIO.output(act.pin, GPIO.HIGH if state else GPIO.LOW)
            return f"✅ {act_id} → {'ON' if state else 'OFF'} (GPIO {act.pin})"
        return f"[SIM] {act_id} → {'ON' if state else 'OFF'}"

    def get_reading(self, sensor_id: str) -> Optional[dict]:
        r = self._readings.get(sensor_id)
        return r.to_dict() if r else None

    def get_all_readings(self) -> dict:
        return {k: v.to_dict() for k, v in self._readings.items()}

    def status(self) -> str:
        i2c = "✅" if self._bus else "⚠️ симуляция"
        gpio = "✅" if GPIO_OK else "⚠️"
        return (
            f"🌿 BIOSPHERE SENSORS:\n"
            f"  I2C bus:   {i2c}\n"
            f"  GPIO:      {gpio}\n"
            f"  Датчиков:  {len(self._readings)}\n"
            f"  Актуаторов:{len(self._actuators)}\n"
            f"  Polling:   {'✅' if self._running else '❌'}"
        )


# ── DAG Node classes (used by biosphere_dag.py pipeline) ─────

class SensorReaderNode:
    """DAG-нода: читает данные со всех датчиков через BiosphereSensorHub."""

    def __init__(self):
        self._hub = BiosphereSensorHub()

    def execute(self, state: dict, core=None) -> dict:
        try:
            readings = self._hub.read_all()
            state["readings"] = readings
            log.debug("SensorReaderNode: %d показаний", len(readings))
        except Exception as e:
            state["error"] = f"SensorReaderNode: {e}"
        return state


class ClimateAnalyzerNode:
    """DAG-нода: анализирует показания и формирует список действий."""

    def execute(self, state: dict, core=None) -> dict:
        readings = state.get("readings", {})
        profile  = state.get("profile", {})
        actions  = []

        for sid, r in readings.items():
            temp = r.get("temperature")
            hum  = r.get("humidity")

            if temp is not None:
                if temp < profile.get("temp_min", 20.0):
                    actions.append(f"heat_on:{sid}")
                elif temp > profile.get("temp_max", 28.0):
                    actions.append(f"cool_on:{sid}")

            if hum is not None:
                if hum < profile.get("hum_min", 50.0):
                    actions.append(f"humidify_on:{sid}")

        state["actions"] = actions
        log.debug("ClimateAnalyzerNode: %d действий", len(actions))
        return state


class ActuatorNode:
    """DAG-нода: исполняет действия (реле, GPIO, умный дом)."""

    def __init__(self):
        self._hub = BiosphereSensorHub()

    def execute(self, state: dict, core=None) -> dict:
        actions   = state.get("actions", [])
        executed  = []

        for action in actions:
            try:
                act_id, *_ = action.split(":")
                result = self._hub.set_actuator(act_id, True)
                executed.append(action)
                log.info("ActuatorNode: %s → %s", action, result)
            except Exception as e:
                log.warning("ActuatorNode: %s failed: %s", action, e)

        state["executed"] = executed
        return state
