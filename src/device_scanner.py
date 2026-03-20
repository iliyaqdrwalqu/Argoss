"""
src/device_scanner.py — Автономный сканер устройства и адаптивный сборщик Argos OS
=====================================================================================
Argos сам определяет тип устройства (CPU, RAM, ОС, периферия, прошивка)
и собирает образ, точно подогнанный под его возможности.

Профили устройств:
  micro     — Embedded MCU (ESP32, RP2040, Arduino) < 512 KB RAM
  lite      — Одноплатник (RPi Zero, ESP32-S3 с PSRAM) ≤ 512 MB
  standard  — RPi 4, Android смартфон, бюджетный ноутбук 1-4 GB RAM
  full      — x86_64 ПК / ноутбук 4-16 GB RAM
  server    — Сервер / рабочая станция > 16 GB RAM

Использование:
    from src.device_scanner import DeviceScanner, AdaptiveImageBuilder

    scanner = DeviceScanner()
    info    = scanner.scan()
    print(scanner.report(info))

    builder = AdaptiveImageBuilder()
    result  = builder.build_for_this_device()
    print(result)

Команды Аргоса:
    скан устройства          — полный отчёт об устройстве
    создай образ для устройства — адаптивный образ под текущий хост
    профиль устройства       — краткий профиль
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from src.argos_logger import get_logger

log = get_logger("argos.device_scanner")


# ══════════════════════════════════════════════════════════════════════════
# ПРОФИЛИ — набор модулей для каждого профиля
# ══════════════════════════════════════════════════════════════════════════

PROFILES: dict[str, dict[str, Any]] = {
    "micro": {
        "label":       "Micro (MCU / ESP32 / Arduino)",
        "ram_max_mb":  512,
        "modules":     ["core", "memory_lite", "mqtt", "serial"],
        "exclude_dirs":["src/interface", "src/connectivity/telegram_bot.py",
                        "src/quantum", "src/knowledge", "src/modules/vision_module.py"],
        "requirements":["requests", "python-dotenv", "pyserial", "paho-mqtt"],
        "description": "Минимальный образ для микроконтроллеров и встроенных систем",
    },
    "lite": {
        "label":       "Lite (RPi Zero / Android low-end / SBC ≤512MB)",
        "ram_max_mb":  512,
        "modules":     ["core", "memory", "mqtt", "p2p", "telegram", "voice_basic"],
        "exclude_dirs":["src/quantum", "src/modules/vision_module.py",
                        "src/interface/streamlit_dashboard.py"],
        "requirements":["requests", "python-dotenv", "psutil", "pyserial",
                        "paho-mqtt", "python-telegram-bot", "pyttsx3",
                        "SpeechRecognition", "packaging", "py7zr"],
        "description": "Лёгкий образ для одноплатников и бюджетных Android",
    },
    "standard": {
        "label":       "Standard (RPi 4 / Android / ноутбук 1-4 GB)",
        "ram_max_mb":  4096,
        "modules":     ["core", "memory", "mqtt", "p2p", "telegram", "voice",
                        "web_dashboard", "iot", "smart_home"],
        "exclude_dirs":["src/quantum/watson_bridge.py"],
        "requirements":["requests", "beautifulsoup4", "python-dotenv", "psutil",
                        "pyserial", "paho-mqtt", "python-telegram-bot",
                        "pyttsx3", "SpeechRecognition", "faster-whisper",
                        "fastapi", "uvicorn", "packaging", "py7zr",
                        "scikit-learn", "numpy", "cryptography"],
        "description": "Стандартный образ — полный IoT + голос + Telegram + веб",
    },
    "full": {
        "label":       "Full (x86_64 ПК / ноутбук 4-16 GB)",
        "ram_max_mb":  16384,
        "modules":     ["all"],
        "exclude_dirs":[],
        "requirements":None,   # все из requirements.txt
        "description": "Полный образ — все модули, ИИ, квантовый мост, Desktop GUI",
    },
    "server": {
        "label":       "Server (>16 GB RAM, многоядерный)",
        "ram_max_mb":  999_999,
        "modules":     ["all", "cluster", "multi_node"],
        "exclude_dirs":[],
        "requirements":None,   # все из requirements.txt
        "description": "Серверный образ — кластеризация, P2P-сеть, полный стек",
    },
}

# ── Специфика по ОС ───────────────────────────────────────────────────────
OS_PROFILES: dict[str, dict] = {
    "Windows": {
        "launchers":   ["launch.bat", "launch.ps1"],
        "bootloader":  "BCD",
        "notes":       "Windows 10/11: двойной клик launch.bat или launch.ps1",
    },
    "Linux": {
        "launchers":   ["launch.sh"],
        "bootloader":  "GRUB",
        "notes":       "Linux: bash launch.sh. GRUB: sudo grub-install ...",
    },
    "Android": {
        "launchers":   ["colab_start.sh"],
        "bootloader":  "fastboot",
        "notes":       "Android: запуск через Termux или как ADB-сервис",
    },
    "Darwin": {
        "launchers":   ["launch.sh"],
        "bootloader":  "EFI",
        "notes":       "macOS: bash launch.sh",
    },
}


# ══════════════════════════════════════════════════════════════════════════
# DEVICE SCANNER
# ══════════════════════════════════════════════════════════════════════════

class DeviceScanner:
    """
    Автономно сканирует аппаратные возможности текущего устройства.

    Собирает:
      • ОС, архитектура, тип прошивки (UEFI/BIOS)
      • CPU: ядра, частота, модель
      • RAM: объём, доступно
      • Хранилище: диски и размеры
      • Сеть: интерфейсы, IP, Wi-Fi
      • Периферия: COM/tty, USB, Audio, GPU, Bluetooth, GPIO
      • Установленные инструменты: esptool, avrdude, adb, fastboot, ...
      • Python-пакеты: какие установлены
      • Определяет профиль: micro / lite / standard / full / server
    """

    def scan(self) -> dict:
        """Полное сканирование устройства. Возвращает структурированный dict."""
        info: dict[str, Any] = {
            "ts":         time.time(),
            "os":         self._scan_os(),
            "cpu":        self._scan_cpu(),
            "ram":        self._scan_ram(),
            "storage":    self._scan_storage(),
            "network":    self._scan_network(),
            "peripherals":self._scan_peripherals(),
            "tools":      self._scan_tools(),
            "packages":   self._scan_packages(),
            "firmware":   self._scan_firmware_type(),
        }
        info["profile"]  = self._determine_profile(info)
        info["os_profile"]= OS_PROFILES.get(info["os"]["system"], OS_PROFILES["Linux"])
        log.info("DeviceScan: %s / %s / %s MB RAM → профиль %s",
                 info["os"]["system"], info["cpu"]["arch"],
                 info["ram"]["total_mb"], info["profile"]["key"])
        return info

    # ── ОС ────────────────────────────────────────────────────────────────
    def _scan_os(self) -> dict:
        is_android = os.path.exists("/system/build.prop")
        sys_name   = "Android" if is_android else platform.system()
        return {
            "system":    sys_name,
            "release":   platform.release(),
            "version":   platform.version()[:80],
            "python":    sys.version.split()[0],
            "is_android":is_android,
            "hostname":  socket.gethostname(),
        }

    # ── CPU ───────────────────────────────────────────────────────────────
    def _scan_cpu(self) -> dict:
        arch     = platform.machine()
        cores    = os.cpu_count() or 1
        model    = "unknown"
        freq_mhz = 0

        # Модель CPU
        try:
            if platform.system() == "Linux":
                txt = Path("/proc/cpuinfo").read_text(errors="ignore")
                for line in txt.split("\n"):
                    if "model name" in line.lower():
                        model = line.split(":")[-1].strip()
                        break
            elif platform.system() == "Windows":
                r = subprocess.run(
                    ["wmic", "cpu", "get", "Name"],
                    capture_output=True, text=True, timeout=5
                )
                lines = [l.strip() for l in r.stdout.split("\n") if l.strip() and "Name" not in l]
                if lines:
                    model = lines[0]
            elif platform.system() == "Darwin":
                r = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True, timeout=3
                )
                model = r.stdout.strip()
        except Exception:
            pass

        # Частота
        try:
            import psutil
            fi = psutil.cpu_freq()
            if fi:
                freq_mhz = int(fi.current)
        except Exception:
            pass

        return {
            "arch":      arch,
            "cores":     cores,
            "model":     model[:80],
            "freq_mhz":  freq_mhz,
            "is_arm":    any(a in arch.lower() for a in ["arm", "aarch"]),
            "is_x86":    any(a in arch.lower() for a in ["x86", "amd64", "i686"]),
            "is_riscv":  "riscv" in arch.lower(),
        }

    # ── RAM ───────────────────────────────────────────────────────────────
    def _scan_ram(self) -> dict:
        total_mb, avail_mb = 0, 0
        try:
            import psutil
            m        = psutil.virtual_memory()
            total_mb = m.total // 1024 // 1024
            avail_mb = m.available // 1024 // 1024
        except Exception:
            try:
                txt = Path("/proc/meminfo").read_text(errors="ignore")
                for line in txt.split("\n"):
                    if "MemTotal" in line:
                        total_mb = int(line.split()[1]) // 1024
                    if "MemAvailable" in line:
                        avail_mb = int(line.split()[1]) // 1024
            except Exception:
                pass
        return {"total_mb": total_mb, "available_mb": avail_mb}

    # ── Хранилище ─────────────────────────────────────────────────────────
    def _scan_storage(self) -> list[dict]:
        disks: list[dict] = []
        try:
            import psutil
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "device":     part.device,
                        "mountpoint": part.mountpoint,
                        "fs":         part.fstype,
                        "total_gb":   round(usage.total / 1024**3, 1),
                        "free_gb":    round(usage.free / 1024**3, 1),
                    })
                except Exception:
                    pass
        except Exception:
            pass
        return disks

    # ── Сеть ──────────────────────────────────────────────────────────────
    def _scan_network(self) -> dict:
        interfaces: list[dict] = []
        has_wifi   = False
        has_eth    = False
        has_bt     = False
        internet   = False

        try:
            import psutil
            for name, addrs in psutil.net_if_addrs().items():
                ips = [a.address for a in addrs if a.family == socket.AF_INET]
                if ips:
                    interfaces.append({"name": name, "ips": ips})
                nl = name.lower()
                if any(w in nl for w in ["wlan", "wifi", "wi-fi", "wireless", "wlp"]):
                    has_wifi = True
                if any(w in nl for w in ["eth", "en0", "ens", "enp"]):
                    has_eth = True
                if "bluetooth" in nl or "bt" in nl:
                    has_bt = True
        except Exception:
            pass

        # Интернет
        try:
            with socket.create_connection(("8.8.8.8", 53), timeout=2):
                internet = True
        except Exception:
            pass

        return {
            "interfaces": interfaces[:6],
            "has_wifi":   has_wifi,
            "has_ethernet":has_eth,
            "has_bluetooth":has_bt,
            "internet":   internet,
        }

    # ── Периферия ─────────────────────────────────────────────────────────
    def _scan_peripherals(self) -> dict:
        serial_ports: list[str] = []
        has_audio  = False
        has_gpu    = False
        has_display= False
        has_gpio   = False
        gpu_name   = ""

        # COM/Serial
        try:
            import serial.tools.list_ports
            serial_ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            # Fallback: /dev/tty*
            try:
                serial_ports = [str(p) for p in Path("/dev").glob("ttyUSB*")]
                serial_ports += [str(p) for p in Path("/dev").glob("ttyACM*")]
            except Exception:
                pass

        # Audio
        has_audio = bool(shutil.which("aplay") or shutil.which("pactl")
                         or shutil.which("python3"))
        try:
            import pyaudio as _pa
            has_audio = True
        except Exception:
            pass

        # GPU
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name",
                                "--format=csv,noheader"],
                               capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                has_gpu  = True
                gpu_name = r.stdout.strip().split("\n")[0][:50]
        except Exception:
            pass
        if not has_gpu:
            try:
                import ctypes
                ctypes.WinDLL("d3d11.dll")
                has_gpu = True
                gpu_name = "DirectX 11 capable"
            except Exception:
                pass

        # Display
        has_display = bool(os.environ.get("DISPLAY") or
                          os.environ.get("WAYLAND_DISPLAY") or
                          platform.system() == "Windows")

        # GPIO (RPi)
        has_gpio = os.path.exists("/dev/gpiomem") or os.path.exists("/sys/class/gpio")

        return {
            "serial_ports": serial_ports[:10],
            "has_audio":    has_audio,
            "has_gpu":      has_gpu,
            "gpu_name":     gpu_name,
            "has_display":  has_display,
            "has_gpio":     has_gpio,
        }

    # ── Инструменты ───────────────────────────────────────────────────────
    def _scan_tools(self) -> dict:
        tool_list = [
            "adb", "fastboot", "heimdall",
            "esptool.py", "avrdude", "avr-gcc",
            "arm-none-eabi-gcc", "openocd", "pio",
            "docker", "git", "ollama",
            "grub-install", "grub-mkrescue", "xorriso",
            "bcdedit",
        ]
        return {
            tool: bool(shutil.which(tool))
            for tool in tool_list
        }

    # ── Python-пакеты ─────────────────────────────────────────────────────
    def _scan_packages(self) -> dict:
        key_pkgs = [
            "requests", "psutil", "fastapi", "uvicorn", "streamlit",
            "pyttsx3", "speech_recognition", "faster_whisper",
            "telegram", "aiogram", "sklearn", "numpy", "cryptography",
            "py7zr", "paho", "serial", "customtkinter",
            "keystone", "capstone", "google.genai", "chromadb",
        ]
        result = {}
        for pkg in key_pkgs:
            try:
                __import__(pkg.replace(".", "_") if "." in pkg else pkg)
                result[pkg] = True
            except ImportError:
                try:
                    __import__(pkg)
                    result[pkg] = True
                except ImportError:
                    result[pkg] = False
        return result

    # ── Тип прошивки ──────────────────────────────────────────────────────
    def _scan_firmware_type(self) -> dict:
        is_efi  = os.path.exists("/sys/firmware/efi")
        fw_type = "UEFI" if is_efi else "BIOS"
        if platform.system() == "Windows":
            try:
                import winreg  # type: ignore[import]
                k = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\SecureBoot\State"
                )
                winreg.CloseKey(k)
                fw_type = "UEFI"
            except Exception:
                fw_type = "BIOS"
        return {"type": fw_type, "is_efi": is_efi}

    # ── Определение профиля ───────────────────────────────────────────────
    def _determine_profile(self, info: dict) -> dict:
        ram_mb   = info["ram"]["total_mb"]
        os_name  = info["os"]["system"]
        is_arm   = info["cpu"]["is_arm"]
        cores    = info["cpu"]["cores"]

        if ram_mb == 0 or ram_mb <= 64:
            key = "micro"
        elif ram_mb <= 512:
            key = "lite"
        elif ram_mb <= 4096:
            key = "standard"
        elif ram_mb <= 16384:
            key = "full"
        else:
            key = "server"

        # Уточнения
        if os_name == "Android":
            key = min(key, "standard", key=lambda k: list(PROFILES).index(k))
        if is_arm and cores <= 2 and ram_mb <= 1024:
            key = "lite"

        profile = dict(PROFILES[key])
        profile["key"] = key
        return profile

    # ── Текстовый отчёт ───────────────────────────────────────────────────
    def report(self, info: dict | None = None) -> str:
        if info is None:
            info = self.scan()

        p   = info["profile"]
        cpu = info["cpu"]
        ram = info["ram"]
        net = info["network"]
        per = info["peripherals"]
        fw  = info["firmware"]
        os_ = info["os"]

        tools_found = sum(1 for v in info["tools"].values() if v)
        pkgs_found  = sum(1 for v in info["packages"].values() if v)
        serial_list = ", ".join(per["serial_ports"][:4]) or "нет"

        lines = [
            "═" * 54,
            f"  🔍 ARGOS DEVICE SCAN — {os_['hostname']}",
            "═" * 54,
            f"  ОС:          {os_['system']} {os_['release']}",
            f"  Python:      {os_['python']}",
            f"  CPU:         {cpu['model'][:50]}",
            f"  Архитектура: {cpu['arch']}  ({cpu['cores']} ядер, {cpu['freq_mhz']} МГц)",
            f"  RAM:         {ram['total_mb']} МБ  (доступно: {ram['available_mb']} МБ)",
            f"  Прошивка:    {fw['type']}",
            "",
            f"  Интернет:    {'✅' if net['internet'] else '❌'}  "
            f"Wi-Fi: {'✅' if net['has_wifi'] else '❌'}  "
            f"Ethernet: {'✅' if net['has_ethernet'] else '❌'}",
            f"  COM-порты:   {serial_list}",
            f"  GPU:         {'✅ ' + per['gpu_name'][:30] if per['has_gpu'] else '❌'}",
            f"  Дисплей:     {'✅' if per['has_display'] else '❌'}",
            f"  Аудио:       {'✅' if per['has_audio'] else '❌'}",
            f"  GPIO:        {'✅' if per['has_gpio'] else '❌ (не RPi)'}",
            "",
            f"  Инструменты: {tools_found}/{len(info['tools'])} найдено",
            f"  Пакеты:      {pkgs_found}/{len(info['packages'])} установлено",
            "",
            "═" * 54,
            f"  📦 ПРОФИЛЬ:  [{p['key'].upper()}] {p['label']}",
            f"  {p['description']}",
            "═" * 54,
        ]

        os_p = info.get("os_profile", {})
        if os_p:
            lines.append(f"  💡 {os_p.get('notes', '')}")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# ADAPTIVE IMAGE BUILDER
# ══════════════════════════════════════════════════════════════════════════

class AdaptiveImageBuilder:
    """
    Собирает образ Argos OS, точно подогнанный под текущее устройство.

    Алгоритм:
      1. DeviceScanner.scan() — получает полный профиль устройства
      2. Выбирает набор модулей по профилю (micro/lite/standard/full/server)
      3. Фильтрует исходники — исключает неподдерживаемые модули
      4. Генерирует requirements.txt только с нужными пакетами
      5. Создаёт ZIP-образ с launch-скриптами под ОС устройства
      6. Добавляет BOOT/ с нужным загрузчиком (GRUB/BCD/fastboot)
      7. Сохраняет device_profile.json в архив
    """

    def __init__(self, output_dir: str = "releases") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._scanner   = DeviceScanner()

    def build_for_this_device(self, version: str = "1.3.0") -> str:
        """
        Полностью автономная сборка образа для текущего устройства.

        Returns:
            str: путь к архиву и описание что включено
        """
        log.info("AdaptiveImageBuilder: сканирование устройства…")
        info    = self._scanner.scan()
        profile = info["profile"]
        os_info = info["os"]
        os_prof = info.get("os_profile", OS_PROFILES["Linux"])

        stamp     = int(time.time())
        pkey      = profile["key"]
        out_name  = f"argos-v{version}-{pkey}-{os_info['system'].lower()}.zip"
        out_path  = self.output_dir / out_name
        prefix    = f"argos-v{version}-{pkey}"

        log.info("Профиль: %s → %s", pkey, out_path.name)

        # Исключить по профилю
        exclude_dirs = set(_GLOBAL_EXCLUDE) | set(profile.get("exclude_dirs", []))

        # Requirements под профиль
        req_list = profile.get("requirements")  # None = все из requirements.txt
        req_text = self._build_requirements(req_list)

        # Launcher скрипты для ОС
        launchers = os_prof.get("launchers", ["launch.sh"])

        file_count = 0
        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                root = Path(".").resolve()

                # Основные файлы
                for item in sorted(root.rglob("*")):
                    if not item.is_file():
                        continue
                    rel = item.relative_to(root)
                    if not self._should_include(rel, exclude_dirs):
                        continue
                    zf.write(item, f"{prefix}/{rel.as_posix()}")
                    file_count += 1

                # requirements адаптированный
                zf.writestr(f"{prefix}/requirements.txt", req_text)

                # device_profile.json — описание профиля
                zf.writestr(
                    f"{prefix}/device_profile.json",
                    json.dumps({
                        "scanned_at":  stamp,
                        "hostname":    info["os"]["hostname"],
                        "os":          info["os"]["system"],
                        "arch":        info["cpu"]["arch"],
                        "ram_mb":      info["ram"]["total_mb"],
                        "firmware":    info["firmware"]["type"],
                        "profile":     pkey,
                        "profile_label": profile["label"],
                        "modules":     profile["modules"],
                        "launchers":   launchers,
                    }, indent=2, ensure_ascii=False)
                )

                # BOOT/ — загрузчик под платформу
                zf.writestr(f"{prefix}/BOOT/README_BOOT.txt",
                            self._boot_readme(info, version))
                if info["os"]["system"] == "Windows":
                    zf.writestr(f"{prefix}/BOOT/bcd_setup.bat",
                                self._bcd_setup_bat(version))
                    zf.writestr(f"{prefix}/BOOT/grub.cfg",
                                self._grub_cfg(version))
                elif info["os"]["system"] == "Android":
                    zf.writestr(f"{prefix}/BOOT/fastboot_guide.txt",
                                self._android_boot_guide())
                else:
                    zf.writestr(f"{prefix}/BOOT/grub.cfg",
                                self._grub_cfg(version))

            size_mb = out_path.stat().st_size / 1024 / 1024
            log.info("Образ создан: %s (%.1f МБ, %d файлов)", out_name, size_mb, file_count)

            launch_hint = self._launch_hint(launchers, prefix)
            report_text = self._scanner.report(info)

            return (
                f"{report_text}\n\n"
                f"📦 ОБРАЗ ARGOS OS СОЗДАН:\n"
                f"  Файл:    {out_path}  ({size_mb:.1f} МБ)\n"
                f"  Профиль: [{pkey.upper()}] {profile['label']}\n"
                f"  Файлов:  {file_count}\n\n"
                f"🚀 Запуск:\n{launch_hint}"
            )

        except Exception as e:
            log.error("build_for_this_device: %s", e)
            return f"❌ Ошибка сборки образа: {e}"

    def build_for_target(self, target: str, version: str = "1.3.0") -> str:
        """
        Собирает образ для указанного профиля вручную.

        Args:
            target: 'micro' | 'lite' | 'standard' | 'full' | 'server'
                    или 'esp32' | 'rpi' | 'android' | 'windows' | 'linux'
        """
        # Маппинг коротких имён → профилей + ОС
        alias_map = {
            "esp32":   ("micro",    "Linux"),
            "esp8266": ("micro",    "Linux"),
            "arduino": ("micro",    "Linux"),
            "rpi_zero":("lite",     "Linux"),
            "rpi0":    ("lite",     "Linux"),
            "rpi":     ("standard", "Linux"),
            "rpi4":    ("standard", "Linux"),
            "android": ("standard", "Android"),
            "windows": ("full",     "Windows"),
            "win10":   ("full",     "Windows"),
            "linux":   ("full",     "Linux"),
            "server":  ("server",   "Linux"),
            "mac":     ("full",     "Darwin"),
            "macos":   ("full",     "Darwin"),
        }
        target_l = target.lower().strip()
        if target_l in alias_map:
            pkey, os_name = alias_map[target_l]
        elif target_l in PROFILES:
            pkey    = target_l
            os_name = platform.system()
        else:
            avail = list(PROFILES) + list(alias_map)
            return f"❌ Неизвестная цель: '{target}'. Доступны: {avail}"

        profile  = dict(PROFILES[pkey])
        profile["key"] = pkey
        os_prof  = OS_PROFILES.get(os_name, OS_PROFILES["Linux"])

        stamp    = int(time.time())
        out_name = f"argos-v{version}-{pkey}-{os_name.lower()}.zip"
        out_path = self.output_dir / out_name
        prefix   = f"argos-v{version}-{pkey}"

        exclude_dirs = set(_GLOBAL_EXCLUDE) | set(profile.get("exclude_dirs", []))
        req_text     = self._build_requirements(profile.get("requirements"))
        launchers    = os_prof.get("launchers", ["launch.sh"])

        file_count = 0
        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                root = Path(".").resolve()
                for item in sorted(root.rglob("*")):
                    if not item.is_file():
                        continue
                    rel = item.relative_to(root)
                    if not self._should_include(rel, exclude_dirs):
                        continue
                    zf.write(item, f"{prefix}/{rel.as_posix()}")
                    file_count += 1

                zf.writestr(f"{prefix}/requirements.txt", req_text)
                zf.writestr(
                    f"{prefix}/device_profile.json",
                    json.dumps({"target": target, "profile": pkey, "os": os_name,
                                "built_at": stamp}, indent=2)
                )
                if os_name == "Windows":
                    zf.writestr(f"{prefix}/BOOT/bcd_setup.bat",
                                self._bcd_setup_bat(version))
                zf.writestr(f"{prefix}/BOOT/grub.cfg", self._grub_cfg(version))

            size_mb = out_path.stat().st_size / 1024 / 1024
            return (
                f"✅ Образ для [{target}] создан:\n"
                f"  {out_path}  ({size_mb:.1f} МБ, {file_count} файлов)\n"
                f"  Профиль: [{pkey.upper()}] {profile['label']}\n"
                f"  Запуск: {' / '.join(launchers)}"
            )
        except Exception as e:
            return f"❌ Ошибка: {e}"

    # ── Вспомогательные ──────────────────────────────────────────────────
    @staticmethod
    def _should_include(rel: Path, exclude_dirs: set) -> bool:
        parts = rel.parts
        for part in parts[:-1]:
            if part in exclude_dirs:
                return False
        name = parts[-1]
        if name.startswith(".") and name not in {".gitignore", ".env.example"}:
            return False
        if name in {".env", "master.key", "node_id", "node_birth",
                    "requirements.txt"}:  # added separately with profile-specific content
            return False
        suffix = Path(name).suffix.lower()
        if suffix in {".pyc", ".pyo", ".db", ".log", ".tmp",
                      ".toc", ".pyz", ".exe", ".dll", ".so"}:
            return False
        # Exclude explicit file paths in exclude_dirs
        rel_str = rel.as_posix()
        for exc in exclude_dirs:
            if rel_str.startswith(exc) or rel_str == exc:
                return False
        return True

    @staticmethod
    def _build_requirements(req_list: list[str] | None) -> str:
        if req_list is None:
            # Читаем основной requirements.txt
            try:
                return Path("requirements.txt").read_text(encoding="utf-8")
            except Exception:
                return "requests\npython-dotenv\npsutil\n"
        header = "# requirements.txt — адаптировано под профиль устройства\n"
        return header + "\n".join(req_list) + "\n"

    @staticmethod
    def _launch_hint(launchers: list[str], prefix: str) -> str:
        hints = []
        for l in launchers:
            if l.endswith(".bat"):
                hints.append(f"  Windows cmd:        cd {prefix} && launch.bat")
            elif l.endswith(".ps1"):
                hints.append(f"  Windows PowerShell: cd {prefix} && .\\launch.ps1")
            else:
                hints.append(f"  Linux/macOS:        cd {prefix} && bash {l}")
        return "\n".join(hints)

    @staticmethod
    def _grub_cfg(version: str) -> str:
        return (
            f"# GRUB2 — Argos OS v{version}\nset timeout=5\nset default=0\n\n"
            f"menuentry 'Argos OS v{version}' {{\n"
            "    set root=(hd0,1)\n"
            "    linux /boot/vmlinuz root=/dev/sda1 quiet splash\n"
            "    initrd /boot/initrd.img\n}\n"
        )

    @staticmethod
    def _bcd_setup_bat(version: str) -> str:
        return (
            "@echo off\nchcp 65001 >nul\n"
            f"echo BCD Setup — Argos OS v{version}\n"
            "bcdedit /set {bootmgr} timeout 10\n"
            "bcdedit /create /d \"Argos OS\" /application bootsector\npause\n"
        )

    @staticmethod
    def _android_boot_guide() -> str:
        return (
            "Android Boot Guide — Argos OS\n\n"
            "1. Установи Termux (F-Droid)\n"
            "2. pkg install python git\n"
            "3. git clone https://github.com/iliyaqdrwalqu/Argoss\n"
            "4. cd Argoss && pip install -r requirements.txt\n"
            "5. python main.py --no-gui\n\n"
            "Для прошивки через fastboot: см. AndroidFlasher\n"
        )

    @staticmethod
    def _boot_readme(info: dict, version: str) -> str:
        p   = info["profile"]
        os_ = info["os"]["system"]
        fw  = info["firmware"]["type"]
        return (
            f"Argos OS v{version} — Boot Guide\n"
            f"Профиль: [{p['key'].upper()}] {p['label']}\n"
            f"ОС: {os_}  Прошивка: {fw}\n\n"
            "Linux GRUB:\n"
            "  sudo grub-install --target=x86_64-efi --efi-directory=/boot/efi\n"
            "  sudo cp BOOT/grub.cfg /boot/grub/grub.cfg\n"
            "  sudo update-grub\n\n"
            "Windows BCD:\n"
            "  Запусти BOOT/bcd_setup.bat от администратора\n\n"
            "USB (dd):\n"
            "  sudo dd if=argos.iso of=/dev/sdX bs=4M status=progress\n"
        )

    def status(self) -> str:
        zips  = list(self.output_dir.glob("*.zip"))
        return (
            f"🔱 AdaptiveImageBuilder:\n"
            f"  Образов: {len(zips)}\n"
            f"  Директория: {self.output_dir}\n"
            f"  Профили: {', '.join(PROFILES)}"
        )


# ── Глобальные исключения ─────────────────────────────────────────────────
_GLOBAL_EXCLUDE = {
    ".git", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".buildozer", "build", "builds",
    "dist", "bin", "data", "logs", ".pytest_cache",
    ".mypy_cache", "releases",
}
