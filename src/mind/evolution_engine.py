"""
src/mind/evolution_engine.py — Движок эволюции Аргоса.

Настоящая эволюция — не генерация кода ради кода, а:
  1. Анализ своих слабых мест (где я ошибаюсь?)
  2. Формулировка гипотезы улучшения
  3. Генерация нового навыка или правила через LLM
  4. Тестирование на синтетических примерах
  5. Принятие/отклонение изменения
  6. Запись в «книгу эволюции» — историю развития

Отличие от src/evolution.py:
  - Тот просто генерирует код по запросу
  - Этот — сам инициирует улучшения, анализируя поведение
"""
from __future__ import annotations

import ast
import json
import os
import time
import threading
import hashlib
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.argos_logger import get_logger

if TYPE_CHECKING:
    from src.core import ArgosCore

log = get_logger("argos.evolution")

EVOLUTION_LOG = Path("data/evolution_history.jsonl")
SKILLS_DIR    = Path("src/skills/evolved")

# Интервал автоэволюции в секундах (0 = только по запросу)
_AUTO_INTERVAL = int(os.getenv("ARGOS_EVOLUTION_INTERVAL", "0"))


class EvolutionRecord:
    """Запись об одном эволюционном изменении."""

    def __init__(self, weakness: str, hypothesis: str,
                 skill_name: str, code: str,
                 accepted: bool, reason: str = ""):
        self.id          = hashlib.md5(f"{weakness}{time.time()}".encode()).hexdigest()[:8]
        self.ts          = datetime.now().isoformat()
        self.weakness    = weakness
        self.hypothesis  = hypothesis
        self.skill_name  = skill_name
        self.code        = code
        self.accepted    = accepted
        self.reason      = reason
        self.test_passed = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "ts": self.ts,
            "weakness": self.weakness,
            "hypothesis": self.hypothesis,
            "skill_name": self.skill_name,
            "code_len": len(self.code),
            "accepted": self.accepted,
            "test_passed": self.test_passed,
            "reason": self.reason,
        }


class EvolutionEngine:
    """
    Движок эволюции — Аргос сам обнаруживает слабые места
    и создаёт навыки для их устранения.
    """

    def __init__(self, core: "ArgosCore"):
        self.core = core
        self._history: list[EvolutionRecord] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()

    def start_auto(self) -> str:
        if _AUTO_INTERVAL == 0:
            return "⚗️ Автоэволюция отключена (ARGOS_EVOLUTION_INTERVAL=0). Вызывай вручную."
        if self._running:
            return "⚗️ Автоэволюция уже активна."
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._auto_loop, daemon=True, name="ArgosEvolution"
        )
        self._thread.start()
        return f"⚗️ Автоэволюция активирована (каждые {_AUTO_INTERVAL}с)."

    def stop_auto(self) -> str:
        self._running = False
        self._stop_event.set()
        return "⚗️ Автоэволюция остановлена."

    # ─────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────

    def evolve(self, target: str = "auto") -> str:
        """
        Один цикл эволюции.
        target: 'auto' — автоопределение слабого места,
                или конкретная область ('память', 'ответы', 'iot')
        """
        # 1. Определяем слабое место
        weakness = self._detect_weakness(target)
        if not weakness:
            return "⚗️ Слабых мест не обнаружено — Аргос работает хорошо."

        log.info("Evolution: слабое место → %s", weakness)

        # 2. Формулируем гипотезу
        hypothesis = self._formulate_hypothesis(weakness)
        if not hypothesis:
            return f"⚗️ Не удалось сформулировать гипотезу для: {weakness}"

        # 3. Генерируем навык
        skill_name, code = self._generate_skill(weakness, hypothesis)
        if not code:
            return f"⚗️ Генерация навыка не удалась: {weakness}"

        # 4. Валидация
        valid, error = self._validate_code(code)
        record = EvolutionRecord(
            weakness=weakness, hypothesis=hypothesis,
            skill_name=skill_name, code=code,
            accepted=valid, reason=error if not valid else "синтаксис OK",
        )

        if valid:
            # 5. Сохраняем навык
            skill_path = SKILLS_DIR / f"{skill_name}.py"
            skill_path.write_text(code, encoding="utf-8")
            record.test_passed = True
            log.info("Evolution: навык сохранён → %s", skill_path)

        # 6. Записываем в историю
        self._history.append(record)
        self._save_record(record)

        return self._format_result(record)

    def detect_weaknesses(self) -> str:
        """Показывает обнаруженные слабые места без генерации кода."""
        weaknesses = []

        # Анализ ошибок в истории диалогов
        if self.core and hasattr(self.core, "memory") and self.core.memory:
            try:
                history = self.core.memory.get_history(limit=50)
                error_count = sum(
                    1 for h in history
                    if any(w in h.get("text", "").lower()
                           for w in ["ошибка", "error", "не могу", "не знаю", "❌"])
                )
                if error_count > 3:
                    weaknesses.append(
                        f"Много ошибок в ответах: {error_count} из последних 50"
                    )
            except Exception:
                pass

        # Проверяем недоступные модули
        missing_modules = []
        for mod in ["chromadb", "sentence_transformers", "faster_whisper"]:
            try:
                __import__(mod)
            except ImportError:
                missing_modules.append(mod)
        if missing_modules:
            weaknesses.append(f"Отсутствуют опциональные модули: {', '.join(missing_modules)}")

        # Проверяем покрытие тестами
        test_dir = Path("tests")
        if test_dir.exists():
            test_count = len(list(test_dir.glob("test_*.py")))
            src_count  = len(list(Path("src").rglob("*.py")))
            ratio = test_count / max(src_count, 1)
            if ratio < 0.3:
                weaknesses.append(
                    f"Низкое покрытие тестами: {test_count} тестов на {src_count} модулей"
                )

        if not weaknesses:
            return "⚗️ Слабых мест не обнаружено."

        lines = ["⚗️ ОБНАРУЖЕННЫЕ СЛАБЫЕ МЕСТА:"]
        for i, w in enumerate(weaknesses, 1):
            lines.append(f"  {i}. {w}")
        return "\n".join(lines)

    def history(self, limit: int = 10) -> str:
        """История эволюционных изменений."""
        if not self._history:
            return "⚗️ История эволюции пуста."
        lines = ["⚗️ ИСТОРИЯ ЭВОЛЮЦИИ:"]
        for r in self._history[-limit:]:
            icon = "✅" if r.accepted else "❌"
            lines.append(
                f"  {icon} [{r.ts[:16]}] {r.skill_name}: {r.weakness[:50]}"
            )
        return "\n".join(lines)

    def status(self) -> str:
        accepted = sum(1 for r in self._history if r.accepted)
        return (
            f"⚗️ ДВИЖОК ЭВОЛЮЦИИ:\n"
            f"  Статус: {'авто-активен' if self._running else 'ручной режим'}\n"
            f"  Всего циклов: {len(self._history)}\n"
            f"  Принято навыков: {accepted}\n"
            f"  Навыки: {SKILLS_DIR}\n"
            f"  Интервал авто: {_AUTO_INTERVAL}с (0=выкл)"
        )

    def list_evolved_skills(self) -> str:
        skills = list(SKILLS_DIR.glob("*.py"))
        if not skills:
            return "⚗️ Эволюционных навыков пока нет."
        lines = ["⚗️ ЭВОЛЮЦИОННЫЕ НАВЫКИ:"]
        for s in skills:
            size = s.stat().st_size
            lines.append(f"  • {s.stem} ({size} байт)")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Внутренняя логика
    # ─────────────────────────────────────────────────────────────────────

    def _auto_loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            self._stop_event.wait(timeout=_AUTO_INTERVAL)
            if not self._running:
                break
            try:
                result = self.evolve("auto")
                log.info("AutoEvolution: %s", result[:80])
            except Exception as e:
                log.warning("AutoEvolution error: %s", e)

    def _detect_weakness(self, target: str) -> str:
        """Определяет слабое место для работы."""
        if target != "auto":
            return target

        # Ищем паттерн ошибок в истории
        if self.core and hasattr(self.core, "memory") and self.core.memory:
            try:
                history = self.core.memory.get_history(limit=30)
                for entry in reversed(history):
                    text = entry.get("text", "").lower()
                    if "не знаю" in text or "не могу ответить" in text:
                        return "пробелы в знаниях — не знаю ответа"
                    if "ошибка" in text and entry.get("role") == "assistant":
                        return "обработка ошибок"
            except Exception:
                pass

        # Случайный выбор области для улучшения
        areas = [
            "улучшение качества ответов на технические вопросы",
            "более точное распознавание намерений пользователя",
            "оптимизация работы с памятью",
            "улучшение форматирования ответов",
        ]
        import random
        return random.choice(areas)

    def _formulate_hypothesis(self, weakness: str) -> str:
        """Формулирует гипотезу через LLM."""
        if not self.core:
            return f"Создать навык для: {weakness}"

        prompt = (
            f"Ты — Аргос, ИИ-система. Обнаружил слабое место: '{weakness}'.\n"
            f"Сформулируй одно конкретное предложение: что именно нужно создать "
            f"как Python-навык чтобы это исправить?\n"
            f"Отвечай одним предложением, без лишних слов."
        )
        try:
            result = self.core._ask_ollama("", prompt)
            if result:
                return result.strip()[:200]
        except Exception:
            pass
        return f"Создать вспомогательный навык для области: {weakness}"

    def _generate_skill(self, weakness: str,
                        hypothesis: str) -> tuple[str, str]:
        """Генерирует Python-навык через LLM."""
        import re
        skill_name = "evolved_" + re.sub(r"\W+", "_", weakness[:20].lower()).strip("_")

        if not self.core:
            return skill_name, ""

        prompt = (
            f"Напиши Python-навык для системы ARGOS.\n"
            f"Проблема: {weakness}\n"
            f"Решение: {hypothesis}\n\n"
            f"Требования к коду:\n"
            f"  - Функция handle(text: str, core=None) -> str | None\n"
            f"  - Если запрос не релевантен — return None\n"
            f"  - SKILL_NAME = '{skill_name}'\n"
            f"  - SKILL_TRIGGERS = ['список', 'триггеров']\n"
            f"  - Graceful imports (try/except для внешних библиотек)\n"
            f"  - Только валидный Python 3.10+ код\n"
            f"  - Без markdown, только чистый код\n\n"
            f"Верни ТОЛЬКО Python-код, без пояснений и без ```."
        )

        try:
            result = self.core._ask_ollama("", prompt)
            if result:
                # Убираем markdown если LLM всё же добавил
                code = result.replace("```python", "").replace("```", "").strip()
                return skill_name, code
        except Exception as e:
            log.warning("Evolution generate: %s", e)

        return skill_name, ""

    def _validate_code(self, code: str) -> tuple[bool, str]:
        """Проверяет синтаксис сгенерированного кода."""
        if not code or len(code) < 20:
            return False, "Код слишком короткий"
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"
        except Exception as e:
            return False, str(e)

    def _format_result(self, record: EvolutionRecord) -> str:
        icon = "✅" if record.accepted else "❌"
        return (
            f"⚗️ ЭВОЛЮЦИЯ [{record.id}]:\n"
            f"  Слабое место: {record.weakness[:60]}\n"
            f"  Гипотеза: {record.hypothesis[:60]}\n"
            f"  Навык: {record.skill_name}\n"
            f"  Результат: {icon} {record.reason}\n"
            f"  {'Навык сохранён в src/skills/evolved/' + record.skill_name + '.py' if record.accepted else 'Навык отклонён'}"
        )

    def _save_record(self, record: EvolutionRecord) -> None:
        try:
            with open(EVOLUTION_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _load_history(self) -> None:
        if not EVOLUTION_LOG.exists():
            return
        try:
            with open(EVOLUTION_LOG, encoding="utf-8") as f:
                for line in f:
                    d = json.loads(line)
                    r = EvolutionRecord(
                        weakness=d.get("weakness", ""),
                        hypothesis=d.get("hypothesis", ""),
                        skill_name=d.get("skill_name", ""),
                        code="",
                        accepted=d.get("accepted", False),
                        reason=d.get("reason", ""),
                    )
                    r.id = d.get("id", "")
                    r.ts = d.get("ts", "")
                    self._history.append(r)
            log.info("Evolution: загружено %d записей", len(self._history))
        except Exception as e:
            log.warning("Evolution load history: %s", e)
