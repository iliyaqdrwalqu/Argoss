"""
otg_manager.py — ARGOS USB OTG Host Manager.

Управление USB-устройствами через Android OTG (USB Host API).
На ПК использует pyserial + lsusb как fallback.

Поддерживает:
  • Обнаружение подключённых USB-устройств (VID/PID/класс)
  • Подключение к USB-Serial (CDC/ACM) адаптерам
  • Отправка/приём данных через OTG-порт
  • Прошивка микроконтроллеров (ESP32/RP2040/STM32) через OTG

Команды ядра:
  otg статус       — состояние OTG
  otg скан         — список подключённых USB-устройств
  otg подключи [id] [baudrate]  — подключиться к USB-Serial
  otg отправь [id] [данные]     — отправить данные
  otg отключи [id] — закрыть соединение
"""
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from src.argos_logger import get_logger

log = get_logger("argos.otg")

IS_ANDROID = os.path.exists("/system/build.prop")

# ── Конфигурация ──────────────────────────────────────────────────────────────
ANDROID_PACKAGE = os.getenv("ARGOS_ANDROID_PACKAGE", "org.sigtrip.argos")

# ── Опциональные зависимости ──────────────────────────────────────────────────

try:
    from jnius import autoclass  # type: ignore
    _UsbManager = autoclass("android.hardware.usb.UsbManager")
    _Context = autoclass("android.content.Context")
    _PythonActivity = autoclass("org.kivy.android.PythonActivity")
    JNIUS_OK = True
except Exception:
    JNIUS_OK = False

try:
    import serial  # type: ignore
    import serial.tools.list_ports as _list_ports  # type: ignore
    SERIAL_OK = True
except ImportError:
    serial = None
    _list_ports = None
    SERIAL_OK = False


# ── Структуры данных ──────────────────────────────────────────────────────────

@dataclass
class OTGDevice:
    """Описание USB-устройства, подключённого через OTG."""
    device_id: str
    vendor_id: int = 0
    product_id: int = 0
    manufacturer: str = ""
    product_name: str = ""
    serial_number: str = ""
    device_class: int = 0
    port: str = ""
    connected: bool = False

    def info(self) -> str:
        vid = f"{self.vendor_id:04X}"
        pid = f"{self.product_id:04X}"
        name = self.product_name or self.manufacturer or "Unknown"
        return (
            f"  [{self.device_id}] VID:{vid} PID:{pid} — {name}"
            + (f" @ {self.port}" if self.port else "")
            + (" ✅" if self.connected else "")
        )


# ── Менеджер OTG ─────────────────────────────────────────────────────────────

class OTGManager:
    """USB OTG Host Manager.

    На Android использует android.hardware.usb.UsbManager через pyjnius.
    На ПК использует pyserial.tools.list_ports как fallback.
    """

    def __init__(self):
        self._devices: Dict[str, OTGDevice] = {}
        self._connections: Dict[str, object] = {}   # id → serial.Serial / UsbDeviceConnection
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitoring = False
        log.info("OTGManager инициализирован (android=%s, serial=%s, jnius=%s)",
                 IS_ANDROID, SERIAL_OK, JNIUS_OK)

    # ── Поддержка OTG ────────────────────────────────────────────────────────

    def is_otg_supported(self) -> bool:
        """Проверяет поддержку USB OTG на устройстве."""
        if IS_ANDROID and JNIUS_OK:
            try:
                ctx = _PythonActivity.mActivity.getApplicationContext()
                pm = ctx.getPackageManager()
                return pm.hasSystemFeature("android.hardware.usb.host")
            except Exception as e:
                log.debug("OTG feature check: %s", e)
                return False
        # На ПК OTG не применимо, но USB-host всегда есть
        return True

    # ── Сканирование устройств ────────────────────────────────────────────────

    def scan_devices(self) -> List[OTGDevice]:
        """Сканирует подключённые USB-устройства."""
        if IS_ANDROID and JNIUS_OK:
            return self._scan_android()
        return self._scan_desktop()

    def _scan_android(self) -> List[OTGDevice]:
        """Сканирование через Android USB Host API."""
        found: List[OTGDevice] = []
        try:
            ctx = _PythonActivity.mActivity.getApplicationContext()
            usb_manager = ctx.getSystemService(_Context.USB_SERVICE)
            device_list = usb_manager.getDeviceList()
            iterator = device_list.values().iterator()
            while iterator.hasNext():
                dev = iterator.next()
                otg_dev = OTGDevice(
                    device_id=str(dev.getDeviceId()),
                    vendor_id=dev.getVendorId(),
                    product_id=dev.getProductId(),
                    manufacturer=str(dev.getManufacturerName() or ""),
                    product_name=str(dev.getProductName() or ""),
                    serial_number=str(dev.getSerialNumber() or ""),
                    device_class=dev.getDeviceClass(),
                    port=dev.getDeviceName(),
                )
                found.append(otg_dev)
        except Exception as e:
            log.warning("Android USB scan error: %s", e)
        with self._lock:
            self._devices = {d.device_id: d for d in found}
        return found

    def _scan_desktop(self) -> List[OTGDevice]:
        """Сканирование через pyserial (ПК/Linux fallback)."""
        found: List[OTGDevice] = []
        if SERIAL_OK:
            try:
                for port in _list_ports.comports():
                    dev = OTGDevice(
                        device_id=port.device,
                        vendor_id=port.vid or 0,
                        product_id=port.pid or 0,
                        manufacturer=port.manufacturer or "",
                        product_name=port.description or "",
                        serial_number=port.serial_number or "",
                        port=port.device,
                    )
                    found.append(dev)
            except Exception as e:
                log.warning("Desktop USB scan error: %s", e)
        else:
            # Попытка lsusb как крайний fallback
            try:
                import subprocess
                r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=3)
                for i, line in enumerate(r.stdout.strip().splitlines()):
                    dev = OTGDevice(device_id=f"usb_{i}", product_name=line.strip())
                    found.append(dev)
            except Exception:
                pass
        with self._lock:
            self._devices = {d.device_id: d for d in found}
        return found

    # ── Подключение к USB-Serial ──────────────────────────────────────────────

    def connect_serial(self, device_id: str, baudrate: int = 115200) -> str:
        """Открывает USB-Serial соединение с устройством."""
        with self._lock:
            dev = self._devices.get(device_id)
        if dev is None:
            # Попробуем интерпретировать device_id как имя порта
            port = device_id
        else:
            port = dev.port or device_id

        if IS_ANDROID and JNIUS_OK:
            return self._connect_android(device_id, baudrate)

        if not SERIAL_OK:
            return "❌ pyserial не установлен. pip install pyserial"

        try:
            conn = serial.Serial(port, baudrate=baudrate, timeout=1)
            with self._lock:
                self._connections[device_id] = conn
                if device_id in self._devices:
                    self._devices[device_id].connected = True
            log.info("OTG Serial подключён: %s @ %d", port, baudrate)
            return f"✅ OTG подключено: {port} @ {baudrate} bps"
        except Exception as e:
            return f"❌ OTG Serial ошибка: {e}"

    def _connect_android(self, device_id: str, baudrate: int) -> str:
        """Подключение через Android UsbDeviceConnection."""
        try:
            ctx = _PythonActivity.mActivity.getApplicationContext()
            usb_manager = ctx.getSystemService(_Context.USB_SERVICE)
            device_list = usb_manager.getDeviceList()
            # Поиск устройства по ID
            iterator = device_list.values().iterator()
            target_dev = None
            while iterator.hasNext():
                dev = iterator.next()
                if str(dev.getDeviceId()) == str(device_id):
                    target_dev = dev
                    break
            if target_dev is None:
                return f"❌ OTG устройство {device_id} не найдено"

            if not usb_manager.hasPermission(target_dev):
                _intent_class = autoclass("android.app.PendingIntent")
                _intent = autoclass("android.content.Intent")
                pi = _intent_class.getBroadcast(
                    ctx, 0,
                    _intent(f"{ANDROID_PACKAGE}.USB_PERMISSION"),
                    _intent_class.FLAG_IMMUTABLE,
                )
                usb_manager.requestPermission(target_dev, pi)
                return "⏳ OTG: запрос разрешения USB. Повторите через секунду."

            conn = usb_manager.openDevice(target_dev)
            if conn is None:
                return "❌ OTG: не удалось открыть устройство"

            with self._lock:
                self._connections[device_id] = conn
                if device_id in self._devices:
                    self._devices[device_id].connected = True

            log.info("Android OTG подключён: %s", device_id)
            return f"✅ OTG (Android) подключено: устройство {device_id}"
        except Exception as e:
            return f"❌ OTG Android ошибка: {e}"

    # ── Передача данных ───────────────────────────────────────────────────────

    def send_data(self, device_id: str, data: str) -> str:
        """Отправляет текстовые данные через OTG-соединение."""
        with self._lock:
            conn = self._connections.get(device_id)
        if conn is None:
            return f"❌ OTG: нет активного соединения с {device_id}"
        try:
            if hasattr(conn, "write"):
                conn.write((data + "\n").encode())
                # Пробуем прочитать ответ
                time.sleep(0.1)
                resp = b""
                if hasattr(conn, "in_waiting") and conn.in_waiting:
                    resp = conn.read(conn.in_waiting)
                resp_text = resp.decode(errors="replace").strip()
                return f"✅ OTG отправлено: {data!r}" + (f"\n↩ {resp_text}" if resp_text else "")
            return "❌ OTG: соединение не поддерживает запись"
        except Exception as e:
            return f"❌ OTG send: {e}"

    # ── Отключение ────────────────────────────────────────────────────────────

    def disconnect(self, device_id: str) -> str:
        """Закрывает OTG-соединение с устройством."""
        with self._lock:
            conn = self._connections.pop(device_id, None)
            if device_id in self._devices:
                self._devices[device_id].connected = False
        if conn is None:
            return f"ℹ️ OTG: соединения с {device_id} не было"
        try:
            conn.close()
        except Exception:
            pass
        return f"✅ OTG отключено: {device_id}"

    # ── Мониторинг (attach/detach) ────────────────────────────────────────────

    def start_monitor(self, on_attach=None, on_detach=None) -> str:
        """Запускает фоновый мониторинг подключения/отключения USB."""
        if self._monitoring:
            return "ℹ️ OTG мониторинг уже запущен"
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(on_attach, on_detach),
            daemon=True,
        )
        self._monitor_thread.start()
        return "✅ OTG мониторинг запущен"

    def stop_monitor(self) -> str:
        """Останавливает мониторинг."""
        self._monitoring = False
        return "✅ OTG мониторинг остановлен"

    def _monitor_loop(self, on_attach, on_detach):
        prev_ids: set = set()
        while self._monitoring:
            try:
                devices = self.scan_devices()
                curr_ids = {d.device_id for d in devices}
                attached = curr_ids - prev_ids
                detached = prev_ids - curr_ids
                for did in attached:
                    log.info("OTG attach: %s", did)
                    if on_attach:
                        on_attach(self._devices.get(did))
                for did in detached:
                    log.info("OTG detach: %s", did)
                    if on_detach:
                        on_detach(did)
                prev_ids = curr_ids
            except Exception as e:
                log.debug("OTG monitor: %s", e)
            time.sleep(3)

    # ── Статус / отчёт ────────────────────────────────────────────────────────

    def status(self) -> str:
        supported = self.is_otg_supported()
        with self._lock:
            devs = list(self._devices.values())
            conns = list(self._connections.keys())
        lines = [
            "🔌 OTG USB HOST MANAGER:",
            f"  Android OTG: {'✅ поддерживается' if supported else '❌ не поддерживается / ПК-режим'}",
            f"  jnius (Android USB API): {'✅' if JNIUS_OK else '❌'}",
            f"  pyserial (ПК fallback): {'✅' if SERIAL_OK else '❌'}",
            f"  Мониторинг: {'✅ активен' if self._monitoring else '⏹ остановлен'}",
            f"  Устройств: {len(devs)}, активных соединений: {len(conns)}",
        ]
        if devs:
            lines.append("  Подключены:")
            for d in devs:
                lines.append(d.info())
        return "\n".join(lines)

    def scan_report(self) -> str:
        """Сканирование и вывод отчёта."""
        devices = self.scan_devices()
        if not devices:
            return "🔌 OTG: USB-устройства не обнаружены."
        lines = [f"🔌 OTG: найдено {len(devices)} USB-устройств:"]
        for d in devices:
            lines.append(d.info())
        return "\n".join(lines)
