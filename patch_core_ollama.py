#!/usr/bin/env python3
"""
patch_core_ollama.py — Добавляет вызов ollama_autoselect в src/core.py.

Запуск: python patch_core_ollama.py
"""
from pathlib import Path
import re
import sys

CORE_PATH = Path("src/core.py")

if not CORE_PATH.exists():
    print("❌ src/core.py не найден. Запусти из корня проекта C:\\argoss\\")
    sys.exit(1)

# Читаем с заменой нечитаемых байт
source = CORE_PATH.read_text(encoding="utf-8", errors="replace")

# ── Патч 1: добавить импорт ollama_autoselect после строки load_dotenv() ──────
IMPORT_MARKER = "load_dotenv()"
IMPORT_PATCH = """load_dotenv()

# [FIX-OLLAMA-AUTO] Автоподбор модели Ollama под железо системы
try:
    from src.ollama_autoselect import autoselect as _ollama_autoselect
    _OLLAMA_AUTOSELECT_OK = True
except Exception:
    _OLLAMA_AUTOSELECT_OK = False"""

if "ollama_autoselect" in source:
    print("⏭️  Импорт ollama_autoselect уже есть — пропускаю патч 1")
elif IMPORT_MARKER in source:
    source = source.replace(IMPORT_MARKER, IMPORT_PATCH, 1)
    print("✅ Патч 1: добавлен импорт ollama_autoselect")
else:
    print("⚠️  Не найден маркер load_dotenv() — патч 1 пропущен")

# ── Патч 2: добавить вызов autoselect в _setup_ai или __init__ ────────────────
# Ищем место где задаётся ollama_url
OLLAMA_URL_MARKER = 'self.ollama_url = os.getenv("OLLAMA_HOST"'

OLLAMA_AUTO_BLOCK = '''        # [FIX-OLLAMA-AUTO] Автоподбор модели под железо
        if _OLLAMA_AUTOSELECT_OK:
            try:
                _sel = _ollama_autoselect(
                    ollama_url=self.ollama_url.replace("/api/generate", ""),
                    auto_pull=os.getenv("ARGOS_OLLAMA_AUTOPULL", "on").lower()
                              not in ("0", "false", "off", "no"),
                )
                log.info("Ollama autoselect: %s (профиль: %s)",
                         _sel["model"], _sel["profile"])
            except Exception as _e:
                log.warning("Ollama autoselect: %s", _e)
'''

if "OLLAMA-AUTO" in source:
    print("⏭️  Вызов autoselect уже есть — пропускаю патч 2")
elif OLLAMA_URL_MARKER in source:
    # Вставляем ПОСЛЕ строки с ollama_url
    idx = source.find(OLLAMA_URL_MARKER)
    # Находим конец строки
    end = source.find("\n", idx) + 1
    source = source[:end] + OLLAMA_AUTO_BLOCK + source[end:]
    print("✅ Патч 2: добавлен вызов autoselect после ollama_url")
else:
    print("⚠️  Не найдена строка self.ollama_url — патч 2 пропущен")
    print("   Добавь вручную в __init__ ArgosCore после задания ollama_url:")
    print(OLLAMA_AUTO_BLOCK)

# ── Патч 3: добавить команду 'ollama статус' в execute_intent ─────────────────
INTENT_MARKER = '"git статус"'   # ищем рядом с git командами

OLLAMA_CMD_BLOCK = '''
        # [FIX-OLLAMA-AUTO] Команды управления Ollama autoselect
        if any(w in t for w in ["ollama статус", "ollama автовыбор", "ollama модель"]):
            try:
                from src.ollama_autoselect import status_report
                return {"answer": status_report(
                    self.ollama_url.replace("/api/generate", "")
                )}
            except Exception as e:
                return {"answer": f"Ollama: {e}"}

        if any(w in t for w in ["ollama авто", "подобрать модель ollama", "выбери модель"]):
            try:
                from src.ollama_autoselect import autoselect
                result = autoselect(
                    ollama_url=self.ollama_url.replace("/api/generate", ""),
                    force=True,
                )
                return {"answer": result["message"]}
            except Exception as e:
                return {"answer": f"Ollama autoselect: {e}"}
'''

if "ollama_autoselect" in source and "ollama статус" in source:
    print("⏭️  Команды ollama уже есть — пропускаю патч 3")
elif INTENT_MARKER in source:
    idx = source.find(INTENT_MARKER)
    # Вставляем перед блоком с git
    line_start = source.rfind("\n", 0, idx) + 1
    source = source[:line_start] + OLLAMA_CMD_BLOCK + source[line_start:]
    print("✅ Патч 3: добавлены команды 'ollama статус' и 'выбери модель'")
else:
    print("⚠️  Маркер git статус не найден — патч 3 пропущен")

# Записываем
CORE_PATH.write_text(source, encoding="utf-8")
print("\n🔱 Готово! Перезапусти: python main.py --no-gui")
print("\nДоступные команды после перезапуска:")
print("  ollama статус      — показать железо и текущую модель")
print("  выбери модель      — принудительный автовыбор")
print("  ollama автовыбор   — то же самое")
