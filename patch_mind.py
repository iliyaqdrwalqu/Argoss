#!/usr/bin/env python3
"""
patch_mind.py — Интегрирует модули разума в src/core.py.

Добавляет:
  - SelfModelV2   — углублённое самосознание
  - Dreamer       — фоновое осмысление опыта
  - EvolutionEngine — реальная эволюция

Запуск: python patch_mind.py
"""
from pathlib import Path
import sys

CORE = Path("src/core.py")
if not CORE.exists():
    print("❌ src/core.py не найден. Запусти из C:\\argoss\\")
    sys.exit(1)

src = CORE.read_text(encoding="utf-8", errors="replace")

# ── Патч 1: импорты ───────────────────────────────────────────────────────────
IMPORT_MARKER = "log = get_logger(\"argos.core\")"
IMPORT_BLOCK = """
# [MIND v2] Модули разума
try:
    from src.mind.dreamer import Dreamer as _Dreamer
    from src.mind.evolution_engine import EvolutionEngine as _EvolutionEngine
    from src.mind.self_model_v2 import SelfModelV2 as _SelfModelV2
    _MIND_OK = True
except Exception as _mind_err:
    _MIND_OK = False
    _mind_err_msg = str(_mind_err)
"""

if "_MIND_OK" in src:
    print("⏭️  Импорты mind уже есть")
elif IMPORT_MARKER in src:
    src = src.replace(IMPORT_MARKER, IMPORT_MARKER + IMPORT_BLOCK, 1)
    print("✅ Патч 1: импорты mind добавлены")
else:
    print("⚠️  Маркер не найден — добавь вручную после get_logger")

# ── Патч 2: инициализация в __init__ ─────────────────────────────────────────
INIT_MARKER = "log.info(\"ArgosCore FINAL v2.0 инициализирован.\")"
INIT_BLOCK = """
        # [MIND v2] Инициализация модулей разума
        self.self_model_v2  = None
        self.dreamer        = None
        self.evolution_engine = None
        if _MIND_OK:
            try:
                self.self_model_v2 = _SelfModelV2(self)
                log.info("SelfModelV2: OK")
            except Exception as e:
                log.warning("SelfModelV2: %s", e)
            try:
                self.dreamer = _Dreamer(self)
                self.dreamer.start()
                log.info("Dreamer: OK")
            except Exception as e:
                log.warning("Dreamer: %s", e)
            try:
                self.evolution_engine = _EvolutionEngine(self)
                log.info("EvolutionEngine: OK")
            except Exception as e:
                log.warning("EvolutionEngine: %s", e)
        else:
            log.warning("Mind modules недоступны: %s", _mind_err_msg)
"""

if "self.dreamer" in src and "self.evolution_engine" in src:
    print("⏭️  Mind инициализация уже есть")
elif INIT_MARKER in src:
    src = src.replace(INIT_MARKER, INIT_BLOCK + "\n        " + INIT_MARKER, 1)
    print("✅ Патч 2: инициализация mind добавлена")
else:
    print("⚠️  Маркер init не найден")

# ── Патч 3: команды в execute_intent ─────────────────────────────────────────
CMD_MARKER = '"git статус"'
CMD_BLOCK = """
        # [MIND v2] Команды разума
        if any(w in t for w in ["кто я", "who am i", "самосознание", "интроспекция"]):
            if self.self_model_v2:
                return {"answer": self.self_model_v2.who_am_i()}
            return {"answer": "SelfModelV2 недоступна."}

        if any(w in t for w in ["биография", "моя история", "что было"]):
            if self.self_model_v2:
                return {"answer": self.self_model_v2.biography.timeline()}
            return {"answer": "Биография недоступна."}

        if any(w in t for w in ["компетенции", "мои способности", "что умею"]):
            if self.self_model_v2:
                return {"answer": self.self_model_v2.competency.report()}
            return {"answer": "Профиль компетенций недоступен."}

        if any(w in t for w in ["эмоция", "настроение аргоса", "как ты себя чувствуешь"]):
            if self.self_model_v2:
                return {"answer": f"Моё состояние: {self.self_model_v2.emotion.describe()}"}
            return {"answer": "Эмоциональная модель недоступна."}

        if any(w in t for w in ["dreamer статус", "осмысление", "сновидение"]):
            if self.dreamer:
                return {"answer": self.dreamer.status()}
            return {"answer": "Dreamer недоступен."}

        if any(w in t for w in ["dreamer запустить", "начни осмысление"]):
            if self.dreamer:
                return {"answer": self.dreamer.force_cycle()}
            return {"answer": "Dreamer недоступен."}

        if any(w in t for w in ["эволюция статус", "история эволюции"]):
            if self.evolution_engine:
                return {"answer": self.evolution_engine.status() + "\\n" +
                        self.evolution_engine.history()}
            return {"answer": "EvolutionEngine недоступен."}

        if any(w in t for w in ["эволюция запустить", "эволюционируй", "улучшись"]):
            if self.evolution_engine:
                return {"answer": self.evolution_engine.evolve()}
            return {"answer": "EvolutionEngine недоступен."}

        if any(w in t for w in ["слабые места", "где я ошибаюсь", "мои слабости"]):
            if self.evolution_engine:
                return {"answer": self.evolution_engine.detect_weaknesses()}
            return {"answer": "EvolutionEngine недоступен."}

        if any(w in t for w in ["сохрани себя", "сохрани модель"]):
            if self.self_model_v2:
                self.self_model_v2.save()
                return {"answer": "✅ Модель самосознания сохранена."}

"""

if "self.self_model_v2" in src and "who_am_i" in src:
    print("⏭️  Команды mind уже есть")
elif CMD_MARKER in src:
    idx = src.find(CMD_MARKER)
    line_start = src.rfind("\n", 0, idx) + 1
    src = src[:line_start] + CMD_BLOCK + src[line_start:]
    print("✅ Патч 3: команды mind добавлены")
else:
    print("⚠️  Маркер команд не найден")

# ── Патч 4: хук on_interaction после каждого ответа ─────────────────────────
RESP_MARKER = "return {\"answer\": answer, \"state\":"
RESP_BLOCK = """
        # [MIND v2] Обновляем самосознание после каждого ответа
        if self.self_model_v2:
            try:
                self.self_model_v2.on_interaction(
                    user_text, answer,
                    success="❌" not in answer and "ошибка" not in answer.lower()
                )
            except Exception:
                pass
"""

if "self.self_model_v2.on_interaction" in src:
    print("⏭️  Хук on_interaction уже есть")
elif RESP_MARKER in src:
    src = src.replace(RESP_MARKER, RESP_BLOCK + "        " + RESP_MARKER, 1)
    print("✅ Патч 4: хук on_interaction добавлен")
else:
    print("⚠️  Маркер ответа не найден — хук не добавлен (некритично)")

# Сохраняем
CORE.write_text(src, encoding="utf-8")
print("\n🔱 Готово! Перезапусти: python main.py --no-gui")
print("\nНовые команды:")
print("  кто я               — глубокая рефлексия")
print("  биография           — история событий")
print("  компетенции         — профиль способностей")
print("  эмоция              — текущее состояние")
print("  dreamer статус      — статус осмысления опыта")
print("  dreamer запустить   — принудительный цикл")
print("  эволюция запустить  — один цикл эволюции")
print("  слабые места        — анализ слабых мест")
print("  сохрани себя        — сохранить модель на диск")
