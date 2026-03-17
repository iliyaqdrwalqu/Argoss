#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
health_check.py — Проверка работоспособности ARGOS v1.3
========================================================
Запуск: python health_check.py

Проверяет:
  1. Наличие ключевых файлов и директорий
  2. Синтаксис Python-модулей
  3. Импорт ключевых модулей
  4. Запуск ядра ArgosCore
  5. Выполнение базовых команд
  6. Доступность ИИ-движков
"""
from __future__ import annotations

import os
import sys
import importlib
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    icon = PASS if ok else FAIL
    line = f"  {icon}  {name}"
    if detail:
        line += f"  ({detail})"
    print(line)
    results.append((name, ok, detail))
    return ok


def section(title: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print("─" * 50)


# ══════════════════════════════════════════════════════
# 1. ФАЙЛЫ И ДИРЕКТОРИИ
# ══════════════════════════════════════════════════════
section("1. Структура проекта")

REQUIRED_FILES = [
    "main.py",
    "genesis.py",
    "requirements.txt",
    "pyproject.toml",
    "build.py",
    "src/core.py",
    "src/argos_logger.py",
    "src/memory.py",
    "src/argos_model.py",
    "src/quantum/logic.py",
    "src/event_bus.py",
    "src/skill_loader.py",
]
REQUIRED_DIRS = [
    "src/security",
    "src/connectivity",
    "src/interface",
    "src/skills",
    "data",
    "logs",
    "tests",
]
for f in REQUIRED_FILES:
    check(f, Path(f).exists())
for d in REQUIRED_DIRS:
    check(d + "/", Path(d).is_dir())

# ══════════════════════════════════════════════════════
# 2. СИНТАКСИС МОДУЛЕЙ
# ══════════════════════════════════════════════════════
section("2. Синтаксис Python-модулей")

py_files = list(Path("src").rglob("*.py"))
syntax_errors = []
for f in py_files:
    try:
        with open(f, encoding="utf-8") as fh:
            source = fh.read()
        compile(source, str(f), "exec")
    except SyntaxError as e:
        syntax_errors.append(f"{f}: {e}")

check(
    f"Синтаксис ({len(py_files)} файлов)",
    len(syntax_errors) == 0,
    f"{len(syntax_errors)} ошибок" if syntax_errors else "OK",
)
for err in syntax_errors[:5]:
    print(f"       {err}")

# ══════════════════════════════════════════════════════
# 3. ИМПОРТ МОДУЛЕЙ
# ══════════════════════════════════════════════════════
section("3. Импорт ключевых модулей")

MODULES = [
    ("src.argos_logger", "get_logger"),
    ("src.quantum.logic", "QuantumEngine"),
    ("src.event_bus", "EventBus"),
    ("src.skill_loader", "SkillLoader"),
    ("src.argos_model", "ArgosOwnModel"),
]
for mod_name, attr in MODULES:
    try:
        mod = importlib.import_module(mod_name)
        ok = hasattr(mod, attr)
        check(f"import {mod_name}", ok, attr if ok else f"нет {attr}")
    except Exception as e:
        check(f"import {mod_name}", False, str(e)[:60])

# ══════════════════════════════════════════════════════
# 4. ЗАПУСК ЯДРА
# ══════════════════════════════════════════════════════
section("4. Запуск ArgosCore")

core = None
try:
    from src.core import ArgosCore
    t0 = time.time()
    core = ArgosCore()
    elapsed = time.time() - t0
    check("ArgosCore.__init__()", True, f"{elapsed:.1f}s, v{core.VERSION}")
    check("core.quantum", core.quantum is not None)
    check("core.memory", core.memory is not None)
    check("core.own_model", core.own_model is not None)
    check("core.git_ops", core.git_ops is not None)
except Exception as e:
    check("ArgosCore", False, str(e)[:80])

# ══════════════════════════════════════════════════════
# 5. БАЗОВЫЕ КОМАНДЫ
# ══════════════════════════════════════════════════════
section("5. Базовые команды ядра")

if core:
    CMD_TESTS = [
        ("статус системы",      lambda r: "CPU" in r),
        ("помощь",              lambda r: "ARGOS" in r or "команд" in r.lower()),
        ("квантовое состояние", lambda r: (
            "Квантов" in r or "состояние" in r.lower()
            or "оффлайн" in r.lower() or "offline" in r.lower()
            or "ядр" in r.lower()
        )),
        ("git статус",          lambda r: "Git" in r or "git" in r.lower()),
        ("модель статус",       lambda r: (
            "модель" in r.lower() or "model" in r.lower()
            or "оффлайн" in r.lower() or "offline" in r.lower()
            or "ядр" in r.lower()
        )),
    ]
    for cmd, validator in CMD_TESTS:
        try:
            result = core.process(cmd)
            answer = result.get("answer", "") if isinstance(result, dict) else str(result)
            ok = validator(answer)
            check(f'"{cmd}"', ok, answer[:60].replace("\n", " ") if not ok else "OK")
        except Exception as e:
            check(f'"{cmd}"', False, str(e)[:60])

# ══════════════════════════════════════════════════════
# 6. ЗАВИСИМОСТИ
# ══════════════════════════════════════════════════════
section("6. Python-зависимости")

# Обязательные (проект не работает без них)
DEPS = [
    ("psutil",      "psutil"),
    ("sklearn",     "scikit-learn"),
    ("numpy",       "numpy"),
    ("requests",    "requests"),
    ("dotenv",      "python-dotenv"),
    ("cryptography","cryptography"),
    ("packaging",   "packaging"),
]
for import_name, pkg_name in DEPS:
    try:
        importlib.import_module(import_name)
        check(pkg_name, True)
    except ImportError:
        check(pkg_name, False, f"pip install {pkg_name}")

# ОПЦИОНАЛЬНЫЕ (предупреждение, не ошибка)
OPTIONAL = [
    ("fastapi",           "fastapi (web dashboard)"),
    ("uvicorn",           "uvicorn (web server)"),
    ("streamlit",         "streamlit (Web UI)"),
    ("google.genai",      "google-genai (Gemini AI)"),
    ("telegram",          "python-telegram-bot (Telegram)"),
    ("customtkinter",     "customtkinter (Desktop GUI)"),
    ("pyttsx3",           "pyttsx3 (TTS голос)"),
    ("speech_recognition","SpeechRecognition (STT)"),
    ("faster_whisper",    "faster-whisper (Whisper STT)"),
    ("paho.mqtt",         "paho-mqtt (MQTT IoT)"),
]
for import_name, label in OPTIONAL:
    try:
        importlib.import_module(import_name)
        check(label, True)
    except ImportError:
        print(f"  {WARN}  {label}  (опционально, pip install {import_name.split('.')[0]})")

# ══════════════════════════════════════════════════════
# 7. ИТОГ
# ══════════════════════════════════════════════════════
print(f"\n{'═' * 50}")
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

if failed == 0:
    print(f"  🔱 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ: {passed}/{total}")
    print("  Аргос полностью готов к запуску!")
    print(f"\n  ▶  python main.py --no-gui")
else:
    print(f"  {FAIL}  Проверки: {passed}/{total} пройдено, {failed} ошибок")
    print("  Исправь ошибки выше и повтори проверку.")
print("═" * 50)

sys.exit(0 if failed == 0 else 1)
