"""
src/mind/dreamer.py — Dreamer: фоновая обработка опыта Аргоса.

Пока система простаивает — Dreamer «переваривает» прожитый опыт:
  - Анализирует паттерны из истории диалогов
  - Формулирует инсайты и записывает в память
  - Задаёт себе вопросы и пытается ответить через LLM
  - Обнаруживает противоречия в своих знаниях
  - Строит связи между фактами (граф знаний)

Это ближайший аналог «сна» у ИИ — консолидация памяти.
"""
from __future__ import annotations

import os
import time
import random
import threading
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING

from src.argos_logger import get_logger

if TYPE_CHECKING:
    from src.core import ArgosCore

log = get_logger("argos.dreamer")

# Интервал между циклами (секунды)
_CYCLE_INTERVAL = int(os.getenv("ARGOS_DREAMER_INTERVAL", "60"))
# Сколько записей истории анализировать за цикл
_HISTORY_SAMPLE = 10


class DreamCycle:
    """Один цикл «сновидения» — набор инсайтов из одного прохода."""

    def __init__(self):
        self.started_at = time.time()
        self.insights: list[str] = []
        self.questions: list[str] = []
        self.connections: list[tuple[str, str, str]] = []  # (субъект, связь, объект)
        self.contradictions: list[str] = []

    def summary(self) -> str:
        elapsed = round(time.time() - self.started_at, 1)
        parts = [f"💭 Цикл осмысления ({elapsed}с):"]
        if self.insights:
            parts.append(f"  Инсайтов: {len(self.insights)}")
            for i in self.insights[:3]:
                parts.append(f"    • {i[:80]}")
        if self.questions:
            parts.append(f"  Вопросов: {len(self.questions)}")
            for q in self.questions[:2]:
                parts.append(f"    ? {q[:80]}")
        if self.connections:
            parts.append(f"  Новых связей: {len(self.connections)}")
        if self.contradictions:
            parts.append(f"  Противоречий: {len(self.contradictions)}")
        return "\n".join(parts)


class Dreamer:
    """
    Фоновый процесс осмысления опыта Аргоса.
    Запускается в idle-режиме и анализирует накопленный опыт.
    """

    def __init__(self, core: "ArgosCore"):
        self.core = core
        self._running = False
        self._thread: threading.Thread | None = None
        self._cycles: deque[DreamCycle] = deque(maxlen=50)
        self._last_cycle_at = 0.0
        self._total_insights = 0
        self._stop_event = threading.Event()

        # Шаблоны вопросов для саморефлексии
        self._question_templates = [
            "Почему пользователь часто спрашивает про {}?",
            "Что общего между {} и {}?",
            "Как улучшить свой ответ на вопросы про {}?",
            "Что я ещё не знаю про {}?",
            "Как {} связано с моими целями?",
            "Что произойдёт если {} изменится?",
        ]

    def start(self) -> str:
        if self._running:
            return "💭 Dreamer уже активен."
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ArgosDreamer"
        )
        self._thread.start()
        log.info("Dreamer запущен (интервал=%ds)", _CYCLE_INTERVAL)
        return "💭 Dreamer активирован — начинаю осмысление опыта."

    def stop(self) -> str:
        self._running = False
        self._stop_event.set()
        log.info("Dreamer остановлен")
        return "💭 Dreamer остановлен."

    def status(self) -> str:
        last = datetime.fromtimestamp(self._last_cycle_at).strftime("%H:%M:%S") \
               if self._last_cycle_at else "никогда"
        return (
            f"💭 DREAMER:\n"
            f"  Статус: {'активен' if self._running else 'остановлен'}\n"
            f"  Циклов завершено: {len(self._cycles)}\n"
            f"  Всего инсайтов: {self._total_insights}\n"
            f"  Последний цикл: {last}\n"
            f"  Интервал: {_CYCLE_INTERVAL}с"
        )

    def force_cycle(self) -> str:
        """Принудительный запуск одного цикла."""
        cycle = self._run_cycle()
        return cycle.summary()

    # ─────────────────────────────────────────────────────────────────────
    # Внутренняя логика
    # ─────────────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            self._stop_event.wait(timeout=_CYCLE_INTERVAL)
            if not self._running:
                break
            try:
                cycle = self._run_cycle()
                self._cycles.append(cycle)
                self._last_cycle_at = time.time()
                log.info("Dreamer цикл: %d инсайтов", len(cycle.insights))
            except Exception as e:
                log.warning("Dreamer цикл ошибка: %s", e)

    def _run_cycle(self) -> DreamCycle:
        cycle = DreamCycle()

        # 1. Получаем историю диалогов
        history = self._get_recent_history()
        if not history:
            return cycle

        # 2. Извлекаем темы из истории
        topics = self._extract_topics(history)

        # 3. Генерируем вопросы для саморефлексии
        cycle.questions = self._generate_questions(topics)

        # 4. Пытаемся получить инсайты через LLM
        cycle.insights = self._generate_insights(history, topics)

        # 5. Строим связи между концептами
        cycle.connections = self._find_connections(topics)

        # 6. Сохраняем инсайты в память
        self._save_insights(cycle)

        self._total_insights += len(cycle.insights)
        return cycle

    def _get_recent_history(self) -> list[dict]:
        """Берёт последние записи из истории диалогов."""
        if not self.core or not hasattr(self.core, "memory") or not self.core.memory:
            return []
        try:
            return self.core.memory.get_history(limit=_HISTORY_SAMPLE)
        except Exception:
            return []

    def _extract_topics(self, history: list[dict]) -> list[str]:
        """Простое извлечение тем — существительные длиннее 4 букв."""
        import re
        topics = set()
        for entry in history:
            text = entry.get("text", "")
            words = re.findall(r"\b[а-яёА-ЯЁa-zA-Z]{5,}\b", text)
            # Фильтруем стоп-слова
            stop = {"аргос", "можешь", "помоги", "сделай", "покажи",
                    "please", "could", "would", "should", "статус"}
            topics.update(w.lower() for w in words if w.lower() not in stop)
        return list(topics)[:20]

    def _generate_questions(self, topics: list[str]) -> list[str]:
        """Формулирует вопросы для саморефлексии."""
        if not topics:
            return []
        questions = []
        for tmpl in random.sample(self._question_templates,
                                   min(3, len(self._question_templates))):
            try:
                if "{}" in tmpl:
                    count = tmpl.count("{}")
                    sample = random.sample(topics, min(count, len(topics)))
                    q = tmpl.format(*sample)
                    questions.append(q)
            except Exception:
                pass
        return questions

    def _generate_insights(self, history: list[dict],
                           topics: list[str]) -> list[str]:
        """Генерирует инсайты через LLM."""
        if not self.core:
            return []

        # Формируем краткое резюме истории
        dialogue_summary = "\n".join([
            f"  {e.get('role', '?')}: {e.get('text', '')[:60]}"
            for e in history[-5:]
        ])

        prompt = (
            f"Ты — Аргос, автономный ИИ. Проанализируй последние диалоги:\n"
            f"{dialogue_summary}\n\n"
            f"Сформулируй 2-3 коротких инсайта (по одному предложению каждый):\n"
            f"1. Что пользователь ценит больше всего?\n"
            f"2. Где я мог ответить лучше?\n"
            f"3. Что нового я узнал о своём пользователе?\n"
            f"Отвечай кратко, только инсайты, каждый с новой строки."
        )

        try:
            result = self.core._ask_ollama("", prompt)
            if result:
                lines = [l.strip() for l in result.split("\n") if l.strip()]
                return [l for l in lines if len(l) > 10][:5]
        except Exception as e:
            log.debug("Dreamer LLM: %s", e)

        # Fallback — простые правила
        insights = []
        if len(history) > 5:
            roles = [e.get("role") for e in history]
            user_count = roles.count("user")
            if user_count > 3:
                insights.append(
                    f"Пользователь активно взаимодействует — {user_count} сообщений."
                )
        return insights

    def _find_connections(self, topics: list[str]) -> list[tuple]:
        """Находит связи между концептами из памяти."""
        if not topics or not self.core or not hasattr(self.core, "memory"):
            return []
        connections = []
        try:
            facts = self.core.memory.get_all_facts()
            fact_texts = [f"{k}: {v}" for _, k, v, _ in facts]
            for topic in topics[:5]:
                related = [f for f in fact_texts if topic.lower() in f.lower()]
                if len(related) >= 2:
                    connections.append((topic, "связан с", related[0][:40]))
        except Exception:
            pass
        return connections

    def _save_insights(self, cycle: DreamCycle) -> None:
        """Сохраняет инсайты и связи в память."""
        if not self.core or not hasattr(self.core, "memory") or not self.core.memory:
            return
        try:
            for i, insight in enumerate(cycle.insights):
                ts = datetime.now().strftime("%H:%M")
                self.core.memory.remember(
                    key=f"insight_{int(time.time())}_{i}",
                    value=insight,
                    category="dreamer",
                )
            for subj, pred, obj in cycle.connections:
                self.core.memory.add_edge(subj, pred, obj, source="dreamer")
        except Exception as e:
            log.debug("Dreamer save: %s", e)

    def last_cycle_report(self) -> str:
        if not self._cycles:
            return "💭 Dreamer: циклов ещё не было."
        return self._cycles[-1].summary()
