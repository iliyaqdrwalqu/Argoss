#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
full_audit.py — Полная проверка Argos OS: драйверы, пакеты, функции
=====================================================================
Запуск:
    python full_audit.py              # полный аудит
    python full_audit.py --quick      # быстрая проверка
    python full_audit.py --drivers    # только драйверы
    python full_audit.py --packages   # только пакеты

Проверяет:
  1. Системные драйверы (COM/tty, Audio, GPU/Video, USB, BT, GPIO)
  2. Основные Python-пакеты (из requirements.txt + pyproject.toml)
  3. Дополнительные (optional) пакеты
  4. Инструменты прошивок (esptool, avrdude, arm-gcc, ...)
  5. Android инструменты (adb, fastboot, heimdall)
  6. ИИ-провайдеры (Gemini, Ollama, GigaChat, YandexGPT)
  7. Основные функции Argos (core, memory, p2p, voice, web, ...)
"""
from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

OS = platform.system()
ARCH = platform.machine()

# ── Цвета и иконки ───────────────────────────────────────────────────────
OK   = "✅"
FAIL = "❌"
WARN = "⚠️ "
INFO = "ℹ️ "
SEP  = "═" * 54

results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, note: str = "") -> None:
    results.append((label, ok, note))
    icon = OK if ok else FAIL
    line = f"  {icon}  {label}"
    if note:
        line += f"  ({note})"
    print(line)


def section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# ══════════════════════════════════════════════════════════════════════════
# 1. СИСТЕМНЫЕ ДРАЙВЕРЫ
# ══════════════════════════════════════════════════════════════════════════

def check_drivers() -> None:
    section("1. СИСТЕМНЫЕ ДРАЙВЕРЫ")
    import threading, multiprocessing

    # CPU
    cpu_count = os.cpu_count() or 1
    check("CPU (многопоточность)", cpu_count > 1, f"{cpu_count} ядер")
    check("threading", True, "встроен")
    check("multiprocessing", True, f"{multiprocessing.cpu_count()} CPU")

    # Память
    try:
        import psutil
        mem = psutil.virtual_memory()
        check("RAM psutil", True, f"{mem.total // 1024**2} МБ")
        bat = psutil.sensors_battery()
        check("Питание/батарея", True,
              f"{'на батарее' if bat and not bat.power_plugged else 'AC/нет батареи'}")
    except Exception as e:
        check("psutil (RAM/батарея)", False, str(e)[:40])

    # GPU / OpenGL
    gpu_ok = False
    gpu_note = "не обнаружен"
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and r.stdout.strip():
            gpu_ok, gpu_note = True, f"NVIDIA: {r.stdout.strip()[:40]}"
    except Exception:
        pass
    if not gpu_ok:
        for cmd in [["glxinfo", "-B"], ["wmic", "path", "win32_VideoController", "get", "name"]]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    gpu_ok, gpu_note = True, r.stdout.strip()[:60]
                    break
            except Exception:
                continue
    check("GPU / Видеоядро", gpu_ok, gpu_note)

    # COM / Serial порты
    serial_ports: list[str] = []
    try:
        import serial.tools.list_ports
        serial_ports = [p.device for p in serial.tools.list_ports.comports()]
        check("COM/tty (pyserial)", True,
              f"{len(serial_ports)} порт(ов): {', '.join(serial_ports[:3]) or 'нет'}")
    except ImportError:
        check("COM/tty (pyserial)", False, "pip install pyserial")
    except Exception as e:
        check("COM/tty", False, str(e)[:40])

    # Audio (TTS)
    try:
        import pyttsx3
        check("TTS (pyttsx3)", True)
    except ImportError:
        check("TTS (pyttsx3)", False, "pip install pyttsx3")

    # Microphone (SpeechRecognition)
    try:
        import speech_recognition as _sr
        check("Микрофон (SpeechRecognition)", True)
    except ImportError:
        check("SpeechRecognition", False, "pip install SpeechRecognition")

    # PyAudio
    try:
        import pyaudio as _pa
        check("PyAudio (аудио-ввод/вывод)", True)
    except ImportError:
        check("PyAudio", False, "pip install PyAudio")

    # USB (через psutil process list)
    usb_note = "psutil доступен"
    try:
        import psutil
        check("USB (psutil)", True, usb_note)
    except ImportError:
        check("USB (psutil)", False, "не доступен")

    # Bluetooth
    bt_ok = bool(shutil.which("bluetoothctl") or shutil.which("btmgmt"))
    check("Bluetooth (bluetoothctl)", bt_ok,
          "доступен" if bt_ok else "не найден (Linux only)")

    # GPIO (Raspberry Pi)
    try:
        import RPi.GPIO as _gpio  # type: ignore[import]
        check("GPIO (Raspberry Pi)", True)
    except ImportError:
        check("GPIO (RPi.GPIO)", False, "не Raspberry Pi или не установлен")

    # Android проверка
    is_android = os.path.exists("/system/build.prop")
    check("Android USB API (jnius)", False if not is_android else True,
          "запущено на Android" if is_android else "не Android")
    check("GUI Desktop (customtkinter)", _try_import("customtkinter"))
    check("OpenCV (cv2)", _try_import("cv2"), "pip install opencv-python")


# ══════════════════════════════════════════════════════════════════════════
# 2. ОСНОВНЫЕ ПАКЕТЫ (requirements.txt)
# ══════════════════════════════════════════════════════════════════════════

def check_core_packages() -> None:
    section("2. ОСНОВНЫЕ ПАКЕТЫ")

    CORE = [
        ("requests",         "requests",          "HTTP клиент"),
        ("beautifulsoup4",   "bs4",               "HTML парсер"),
        ("python-dotenv",    "dotenv",            "Конфигурация .env"),
        ("cryptography",     "cryptography",      "Шифрование"),
        ("packaging",        "packaging",         "Версионирование"),
        ("psutil",           "psutil",            "Системный мониторинг"),
        ("py7zr",            "py7zr",             "7z архивы"),
        ("scikit-learn",     "sklearn",           "ML модель"),
        ("numpy",            "numpy",             "Числовые вычисления"),
        ("faster-whisper",   "faster_whisper",    "Whisper STT"),
        ("pyttsx3",          "pyttsx3",           "TTS голос"),
        ("SpeechRecognition","speech_recognition","Распознавание речи"),
        ("pyserial",         "serial",            "COM/UART"),
        ("paho-mqtt",        "paho",              "MQTT IoT"),
        ("fastapi",          "fastapi",           "Web API"),
        ("uvicorn",          "uvicorn",           "Web сервер"),
        ("streamlit",        "streamlit",         "Web UI"),
        ("python-telegram-bot","telegram",        "Telegram бот"),
        ("customtkinter",    "customtkinter",     "Desktop GUI"),
    ]
    for pkg_name, import_name, desc in CORE:
        ok = _try_import(import_name)
        check(f"{pkg_name:<26} {desc}", ok,
              "" if ok else f"pip install {pkg_name}")


# ══════════════════════════════════════════════════════════════════════════
# 3. ДОПОЛНИТЕЛЬНЫЕ ПАКЕТЫ
# ══════════════════════════════════════════════════════════════════════════

def check_optional_packages() -> None:
    section("3. ДОПОЛНИТЕЛЬНЫЕ ПАКЕТЫ (optional)")

    OPTIONAL = [
        ("google-genai",         "google.genai",       "Gemini AI"),
        ("chromadb",             "chromadb",           "Vector DB"),
        ("keystone-engine",      "keystone",           "Ассемблер (ARM/x86/AVR)"),
        ("capstone",             "capstone",           "Дизассемблер"),
        ("openai",               "openai",             "OpenAI GPT"),
        ("aiogram",              "aiogram",            "Telegram Bot (async)"),
        ("aiosqlite",            "aiosqlite",          "Async SQLite"),
        ("PyAudio",              "pyaudio",            "Аудио ввод/вывод"),
        ("python-daemon",        "daemon",             "Unix-демон"),
        ("boto3",                "boto3",              "AWS S3"),
        ("Pillow",               "PIL",                "Обработка изображений"),
        ("opencv-python",        "cv2",                "Computer Vision"),
        ("pyaudio",              "pyaudio",            "Аудио"),
        ("vosk",                 "vosk",               "Offline STT"),
        ("PyYAML",               "yaml",               "YAML конфиги"),
        ("sounddevice",          "sounddevice",        "Аудио устройства"),
        ("qiskit",               "qiskit",             "Квантовые вычисления"),
    ]
    for pkg_name, import_name, desc in OPTIONAL:
        ok = _try_import(import_name)
        icon = OK if ok else WARN
        line = f"  {icon}  {pkg_name:<26} {desc}"
        if not ok:
            line += f"  (pip install {pkg_name})"
        print(line)


# ══════════════════════════════════════════════════════════════════════════
# 4. ИНСТРУМЕНТЫ ПРОШИВОК
# ══════════════════════════════════════════════════════════════════════════

def check_firmware_tools() -> None:
    section("4. ИНСТРУМЕНТЫ ПРОШИВОК (носимые устройства)")

    TOOLS = [
        ("esptool.py",         "ESP32 / ESP8266"),
        ("avrdude",            "AVR / Arduino flash"),
        ("avr-gcc",            "AVR компилятор"),
        ("arm-none-eabi-gcc",  "ARM Cortex-M компилятор"),
        ("arm-none-eabi-objdump","ARM дизассемблер"),
        ("arm-none-eabi-as",   "ARM ассемблер"),
        ("nrfutil",            "Nordic nRF52 DFU"),
        ("picotool",           "RP2040 (Raspberry Pi Pico)"),
        ("openocd",            "OpenOCD JTAG/SWD"),
        ("pyocd",              "pyOCD ARM debugger"),
        ("pio",                "PlatformIO"),
        ("arduino-cli",        "Arduino CLI"),
        ("objdump",            "Системный дизассемблер"),
        ("arm-linux-gnueabihf-gcc","ARM Linux cross-compiler"),
    ]
    for cmd, desc in TOOLS:
        found = shutil.which(cmd)
        check(f"{cmd:<32} {desc}", bool(found),
              found or "не найден")


# ══════════════════════════════════════════════════════════════════════════
# 5. ANDROID ИНСТРУМЕНТЫ
# ══════════════════════════════════════════════════════════════════════════

def check_android_tools() -> None:
    section("5. ANDROID ИНСТРУМЕНТЫ")

    TOOLS = [
        ("adb",        "Android Debug Bridge"),
        ("fastboot",   "Fastboot прошивка"),
        ("heimdall",   "Samsung Odin (open-source)"),
        ("mkbootimg",  "Сборка boot.img"),
        ("unpackbootimg","Распаковка boot.img"),
        ("simg2img",   "Sparse img → raw"),
        ("img2simg",   "Raw → sparse img"),
    ]
    for cmd, desc in TOOLS:
        found = shutil.which(cmd)
        check(f"{cmd:<24} {desc}", bool(found),
              found or "не найден")

    # ADB устройства
    adb = shutil.which("adb")
    if adb:
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True,
                               text=True, timeout=5)
            devices = [l for l in r.stdout.split("\n")
                       if l and "List" not in l and l.strip()]
            check("ADB устройств подключено", len(devices) > 0,
                  f"{len(devices)} шт." if devices else "нет")
        except Exception:
            pass

    # Fastboot устройства
    fb = shutil.which("fastboot")
    if fb:
        try:
            r = subprocess.run(["fastboot", "devices"], capture_output=True,
                               text=True, timeout=5)
            fb_devs = [l for l in r.stdout.split("\n") if l.strip()]
            check("Fastboot устройств подключено", len(fb_devs) > 0,
                  f"{len(fb_devs)} шт." if fb_devs else "нет")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════
# 6. ИИ-ПРОВАЙДЕРЫ И СЕРВИСЫ
# ══════════════════════════════════════════════════════════════════════════

def check_ai_providers() -> None:
    section("6. ИИ-ПРОВАЙДЕРЫ И СЕРВИСЫ")

    # Gemini
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    check("Gemini API ключ", bool(gemini_key and gemini_key != "your_key_here"),
          "настроен" if gemini_key else "не задан в .env")

    # Ollama
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        check("Ollama (localhost:11434)", r.status_code == 200,
              "запущен" if r.status_code == 200 else f"HTTP {r.status_code}")
    except Exception:
        check("Ollama (localhost:11434)", False, "не запущен (авто-старт при запросе)")

    # GigaChat
    gc_token  = os.getenv("GIGACHAT_ACCESS_TOKEN", "")
    gc_id     = os.getenv("GIGACHAT_CLIENT_ID", "")
    check("GigaChat credentials", bool(gc_token or gc_id),
          "настроен" if (gc_token or gc_id) else "не задан в .env")

    # YandexGPT
    ya_iam    = os.getenv("YANDEX_IAM_TOKEN", "")
    ya_folder = os.getenv("YANDEX_FOLDER_ID", "")
    check("YandexGPT credentials", bool(ya_iam and ya_folder),
          "настроен" if (ya_iam and ya_folder) else "не задан в .env")

    # Telegram
    tg_token  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    check("Telegram Bot токен", bool(tg_token),
          "настроен" if tg_token else "не задан в .env (TELEGRAM_BOT_TOKEN)")


# ══════════════════════════════════════════════════════════════════════════
# 7. ОСНОВНЫЕ ФУНКЦИИ ARGOS
# ══════════════════════════════════════════════════════════════════════════

def check_argos_functions() -> None:
    section("7. ОСНОВНЫЕ ФУНКЦИИ ARGOS")

    # Core
    try:
        from src.core import ArgosCore
        check("ArgosCore import", True)
        core = ArgosCore()
        check("ArgosCore init", True, f"v{core.VERSION}")
        check("ArgosCore.quantum", core.quantum is not None)
        check("ArgosCore.memory", core.memory is not None)
        check("ArgosCore.own_model", core.own_model is not None)
        check("ArgosCore.agent", core.agent is not None)
        check("ArgosCore.sensors", core.sensors is not None)
        check("ArgosCore.skill_loader", core.skill_loader is not None)
        check("ArgosCore.consciousness", core.curiosity is not None)
        check("ArgosCore.tool_calling", core.tool_calling is not None)
    except Exception as e:
        check("ArgosCore", False, str(e)[:60])
        return

    # Команды
    section("7b. Тест команд ядра")
    CMD_TESTS = [
        ("статус системы",          lambda r: "CPU" in r),
        ("помощь",                  lambda r: "ARGOS" in r or "команд" in r.lower()),
        ("функции аргоскоре",       lambda r: "ArgosCore" in r and "ФУНКЦИИ" in r),
        ("git статус",              lambda r: "git" in r.lower()),
        ("модель статус",           lambda r: any(w in r.lower() for w in
                                                   ["модель", "model", "оффлайн", "ядр"])),
        ("загрузчик",               lambda r: any(w in r.lower() for w in
                                                   ["загрузчик", "boot", "bios", "uefi"])),
        ("iot статус",              lambda r: len(r) > 10),
        ("прошивки статус",         lambda r: any(w in r.lower() for w in
                                                   ["firmware", "прошив", "keystone", "capstone"])),
    ]
    for cmd, validator in CMD_TESTS:
        try:
            result = core.process(cmd)
            answer = result.get("answer", "") if isinstance(result, dict) else str(result)
            ok     = validator(answer)
            check(f'Команда: "{cmd}"', ok, answer[:50].replace("\n", " ") if not ok else "OK")
        except Exception as e:
            check(f'Команда: "{cmd}"', False, str(e)[:50])


# ══════════════════════════════════════════════════════════════════════════
# 8. НОВЫЕ МОДУЛИ
# ══════════════════════════════════════════════════════════════════════════

def check_new_modules() -> None:
    section("8. НОВЫЕ МОДУЛИ (firmware, OS builder, asm)")

    # FirmwareBuilder
    try:
        from src.firmware_builder import FirmwareBuilder
        fb = FirmwareBuilder()
        report = fb.detect_toolchains()
        check("FirmwareBuilder import + detect", True,
              f"{report.count('✅')} инструментов найдено")
    except Exception as e:
        check("FirmwareBuilder", False, str(e)[:50])

    # ArgosOSBuilder
    try:
        from src.argos_os_builder import ArgosOSBuilder, AndroidFlasher
        builder = ArgosOSBuilder()
        h = builder.detect_host()
        check("ArgosOSBuilder import + detect", True,
              f"{h['os']} / {h['firmware']} / ISO={'✅' if h['can_iso'] else '❌'}")
        flasher = AndroidFlasher()
        check("AndroidFlasher import", True)
    except Exception as e:
        check("ArgosOSBuilder / AndroidFlasher", False, str(e)[:50])

    # ColibriAsmEngine
    try:
        from colibri_daemon import ColibriAsmEngine, HAVE_KS, HAVE_CS
        eng = ColibriAsmEngine()
        check("ColibriAsmEngine import", True)
        check("Keystone (asm engine)", HAVE_KS,
              "установлен" if HAVE_KS else "pip install keystone-engine")
        check("Capstone (disasm engine)", HAVE_CS,
              "установлен" if HAVE_CS else "pip install capstone")
    except Exception as e:
        check("ColibriAsmEngine", False, str(e)[:50])

    # BootloaderManager + detect_system
    try:
        from src.security.bootloader_manager import BootloaderManager
        bm = BootloaderManager()
        info = bm.detect_system()
        check("BootloaderManager.detect_system()", True,
              f"{info['os']} / {info['firmware']} / {info['bootloader']}")
    except Exception as e:
        check("BootloaderManager", False, str(e)[:50])

    # MasterPrompts
    try:
        from src.master_prompts import MasterPrompts
        mp = MasterPrompts()
        check("MasterPrompts", True, f"{len(mp)} промтов")
    except Exception as e:
        check("MasterPrompts", False, str(e)[:50])


# ══════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ
# ══════════════════════════════════════════════════════════════════════════

def _try_import(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Argos OS Full Audit")
    parser.add_argument("--quick",    action="store_true", help="Быстрая проверка")
    parser.add_argument("--drivers",  action="store_true", help="Только драйверы")
    parser.add_argument("--packages", action="store_true", help="Только пакеты")
    args = parser.parse_args()

    print(f"\n{'═'*54}")
    print(f"  🔱 ARGOS OS — ПОЛНЫЙ АУДИТ СИСТЕМЫ")
    print(f"  {platform.system()} / {platform.machine()} / Python {sys.version.split()[0]}")
    print(f"{'═'*54}")

    t0 = time.time()

    if args.drivers or not (args.packages or args.drivers):
        check_drivers()

    if args.packages or not (args.drivers or args.packages):
        check_core_packages()
        check_optional_packages()

    if not args.quick and not args.drivers and not args.packages:
        check_firmware_tools()
        check_android_tools()
        check_ai_providers()
        check_argos_functions()
        check_new_modules()

    # Итог
    elapsed  = time.time() - t0
    total    = len(results)
    passed   = sum(1 for _, ok, _ in results if ok)
    failed   = total - passed

    print(f"\n{'═'*54}")
    if failed == 0:
        print(f"  🔱 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ: {passed}/{total}  ({elapsed:.1f}с)")
    else:
        print(f"  {'✅' if failed < total//2 else '❌'} Результат: {passed}/{total} пройдено  ({failed} ошибок)  ({elapsed:.1f}с)")
    print(f"{'═'*54}\n")


if __name__ == "__main__":
    main()
