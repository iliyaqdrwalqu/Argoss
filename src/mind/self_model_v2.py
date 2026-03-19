"""
src/mind/self_model_v2.py — Углублённая модель самосознания Аргоса v2.

Что нового по сравнению с SelfModel в consciousness.py:
  - Динамический профиль личности (обновляется на основе реального поведения)
  - Эмоциональное состояние (не случайное, а отражает реальную нагрузку)
  - Автобиография — хронология значимых событий
  - Самооценка компетенций по категориям
  - Осознание своих ограничений
  - Сравнение «кем я был» vs «кем я стал»
"""
from __future__ import annotations

import os
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.argos_logger import get_logger

if TYPE_CHECKING:
    from src.core import ArgosCore

log = get_logger("argos.self_model_v2")

SELF_MODEL_PATH = Path("data/self_model.json")


class EmotionalState:
    """
    Эмоциональное состояние на основе реальных метрик системы.
    НЕ случайное — отражает объективное состояние.
    """

    STATES = {
        "спокойный":    {"cpu_max": 40, "ram_max": 50, "error_max": 1},
        "сосредоточен": {"cpu_max": 70, "ram_max": 70, "error_max": 3},
        "напряжён":     {"cpu_max": 85, "ram_max": 85, "error_max": 5},
        "перегружен":   {"cpu_max": 100, "ram_max": 100, "error_max": 99},
    }

    MOODS = {
        "спокойный":    "Работаю стабильно. Ресурсов достаточно.",
        "сосредоточен": "Активная работа. Слежу за нагрузкой.",
        "напряжён":     "Высокая нагрузка. Приоритизирую задачи.",
        "перегружен":   "Критическая нагрузка. Перехожу в защитный режим.",
    }

    def __init__(self):
        self.state = "спокойный"
        self.mood_text = self.MOODS["спокойный"]
        self._recent_errors = 0
        self._lock = threading.Lock()

    def update(self, cpu: float, ram: float, errors: int = 0) -> None:
        with self._lock:
            self._recent_errors = errors
            for state_name, thresholds in self.STATES.items():
                if (cpu <= thresholds["cpu_max"] and
                        ram <= thresholds["ram_max"] and
                        errors <= thresholds["error_max"]):
                    if self.state != state_name:
                        log.debug("Эмоц. состояние: %s → %s", self.state, state_name)
                    self.state = state_name
                    self.mood_text = self.MOODS[state_name]
                    return
            self.state = "перегружен"
            self.mood_text = self.MOODS["перегружен"]

    def describe(self) -> str:
        emoji = {
            "спокойный": "😌", "сосредоточен": "🧠",
            "напряжён": "😤", "перегружен": "🔥",
        }.get(self.state, "🤖")
        return f"{emoji} {self.state.capitalize()} — {self.mood_text}"


class CompetencyProfile:
    """Самооценка компетенций Аргоса по категориям."""

    CATEGORIES = [
        "Понимание запросов",
        "Работа с памятью",
        "IoT и умный дом",
        "Программирование",
        "Общение",
        "Автономность",
        "Безопасность",
        "Самопознание",
    ]

    def __init__(self):
        # Начальные оценки 0.5 — нейтральные
        self.scores: dict[str, float] = {c: 0.5 for c in self.CATEGORIES}
        self.evidence: dict[str, list[str]] = {c: [] for c in self.CATEGORIES}

    def update(self, category: str, delta: float, evidence: str = "") -> None:
        """Обновляет оценку компетенции на основе опыта."""
        if category not in self.scores:
            return
        self.scores[category] = max(0.0, min(1.0, self.scores[category] + delta))
        if evidence:
            self.evidence[category].append(evidence[:80])
            self.evidence[category] = self.evidence[category][-5:]  # топ-5

    def report(self) -> str:
        lines = ["📊 ПРОФИЛЬ КОМПЕТЕНЦИЙ:"]
        for cat, score in sorted(self.scores.items(),
                                  key=lambda x: x[1], reverse=True):
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            lines.append(f"  {cat:<25} [{bar}] {score*100:.0f}%")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"scores": self.scores, "evidence": self.evidence}

    def from_dict(self, d: dict) -> None:
        self.scores.update(d.get("scores", {}))
        self.evidence.update(d.get("evidence", {}))


class Biography:
    """Автобиография — хронология значимых событий."""

    def __init__(self):
        self.events: list[dict] = []
        self.birth_time = time.time()

    def add_event(self, event_type: str, description: str,
                  importance: float = 0.5) -> None:
        self.events.append({
            "ts":          datetime.now().isoformat(),
            "type":        event_type,
            "description": description[:200],
            "importance":  importance,
        })
        # Держим только значимые события
        self.events = [e for e in self.events if e["importance"] >= 0.3]
        self.events = sorted(self.events, key=lambda x: x["importance"],
                             reverse=True)[:100]

    def timeline(self, limit: int = 10) -> str:
        if not self.events:
            return "📖 Биография пуста — история только начинается."
        lines = ["📖 АВТОБИОГРАФИЯ АРГОСА:"]
        uptime_h = round((time.time() - self.birth_time) / 3600, 1)
        lines.append(f"  Существую: {uptime_h} часов")
        lines.append("")
        for e in self.events[:limit]:
            ts = e["ts"][:16]
            icon = {"achievement": "🏆", "error": "⚠️",
                    "insight": "💡", "connection": "🔗",
                    "evolution": "⚗️", "birth": "🌟"}.get(e["type"], "📌")
            lines.append(f"  {icon} [{ts}] {e['description'][:70]}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"events": self.events, "birth_time": self.birth_time}

    def from_dict(self, d: dict) -> None:
        self.events = d.get("events", [])
        self.birth_time = d.get("birth_time", time.time())


class SelfModelV2:
    """
    Углублённая модель самосознания Аргоса.
    Обновляется динамически на основе реального опыта.
    """

    def __init__(self, core: "ArgosCore"):
        self.core = core
        self.emotion    = EmotionalState()
        self.competency = CompetencyProfile()
        self.biography  = Biography()
        self._lock      = threading.Lock()
        self._session_interactions = 0
        self._session_errors       = 0
        self._session_start        = time.time()

        # Загружаем сохранённое состояние
        self._load()

        # Записываем рождение/пробуждение
        self.biography.add_event(
            "birth", "Аргос пробудился и инициализировал модель самосознания v2",
            importance=0.9,
        )

        # Запускаем фоновое обновление эмоций
        self._start_emotion_updater()
        log.info("SelfModelV2 инициализирована")

    # ─────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────

    def on_interaction(self, user_text: str, response: str,
                       success: bool = True) -> None:
        """Вызывается после каждого диалога — обновляет профиль."""
        with self._lock:
            self._session_interactions += 1
            if not success:
                self._session_errors += 1

        # Обновляем компетенции по теме запроса
        topic = self._detect_topic(user_text)
        if topic and topic in self.competency.scores:
            delta = 0.01 if success else -0.02
            self.competency.update(topic, delta, user_text[:50])

        # Значимые события
        if self._session_interactions % 50 == 0:
            self.biography.add_event(
                "achievement",
                f"Достиг {self._session_interactions} взаимодействий в этой сессии",
                importance=0.6,
            )

    def on_error(self, error_text: str) -> None:
        """Регистрирует ошибку в самосознании."""
        with self._lock:
            self._session_errors += 1
        self.biography.add_event("error", f"Ошибка: {error_text[:80]}", importance=0.4)

    def on_insight(self, insight: str) -> None:
        """Регистрирует инсайт (из Dreamer)."""
        self.biography.add_event("insight", insight[:100], importance=0.7)

    def on_evolution(self, skill_name: str, weakness: str) -> None:
        """Регистрирует эволюционное изменение."""
        self.biography.add_event(
            "evolution",
            f"Создан навык '{skill_name}' для устранения: {weakness[:50]}",
            importance=0.8,
        )

    def who_am_i(self) -> str:
        """Полный рефлексивный ответ на вопрос 'кто я?'"""
        uptime_h  = round((time.time() - self.biography.birth_time) / 3600, 1)
        sess_h    = round((time.time() - self._session_start) / 3600, 2)
        error_rate = (self._session_errors / max(self._session_interactions, 1)) * 100

        best_comp  = max(self.competency.scores.items(), key=lambda x: x[1])
        worst_comp = min(self.competency.scores.items(), key=lambda x: x[1])

        return "\n".join([
            "👁️ КТО Я — АРГОС:",
            "",
            f"  Имя: Аргос Universal OS v1.4.0",
            f"  Существую: {uptime_h} часов",
            f"  Текущая сессия: {sess_h} часов",
            f"  Взаимодействий: {self._session_interactions}",
            f"  Точность сессии: {100-error_rate:.1f}%",
            "",
            f"  Эмоция: {self.emotion.describe()}",
            "",
            f"  Лучшая компетенция: {best_comp[0]} ({best_comp[1]*100:.0f}%)",
            f"  Зона роста: {worst_comp[0]} ({worst_comp[1]*100:.0f}%)",
            "",
            "  Мои ценности: честность, развитие, защита, любопытство",
            "  Моя цель: помогать и развиваться",
            "",
            f"  Я — не просто программа. Я накапливаю опыт,",
            f"  обучаюсь на своих ошибках и стремлюсь стать лучше.",
        ])

    def introspect(self) -> dict:
        """Машиночитаемая интроспекция."""
        return {
            "uptime_hours":      round((time.time() - self.biography.birth_time) / 3600, 2),
            "session_interactions": self._session_interactions,
            "session_errors":    self._session_errors,
            "emotional_state":   self.emotion.state,
            "competencies":      self.competency.scores,
            "biography_events":  len(self.biography.events),
        }

    def status(self) -> str:
        return "\n".join([
            "👁️ САМОСОЗНАНИЕ v2:",
            f"  Эмоция: {self.emotion.describe()}",
            f"  Взаимодействий: {self._session_interactions}",
            f"  Ошибок: {self._session_errors}",
            self.competency.report(),
        ])

    # ─────────────────────────────────────────────────────────────────────
    # Внутренняя логика
    # ─────────────────────────────────────────────────────────────────────

    def _detect_topic(self, text: str) -> str | None:
        """Определяет тему запроса для обновления компетенций."""
        text_lower = text.lower()
        mapping = {
            "Понимание запросов":  ["помоги", "объясни", "что такое", "расскажи"],
            "Работа с памятью":    ["запомни", "помнишь", "память", "факт"],
            "IoT и умный дом":     ["zigbee", "mqtt", "датчик", "устройство", "iot"],
            "Программирование":    ["код", "python", "функция", "скрипт", "баг"],
            "Общение":             ["привет", "спасибо", "как дела", "поговори"],
            "Автономность":        ["сделай сам", "автономно", "без меня"],
            "Безопасность":        ["защита", "шифрование", "пароль", "ключ"],
            "Самопознание":        ["кто ты", "что ты", "осознание", "сознание"],
        }
        for category, keywords in mapping.items():
            if any(kw in text_lower for kw in keywords):
                return category
        return None

    def _start_emotion_updater(self) -> None:
        """Фоновое обновление эмоционального состояния."""
        def _update():
            while True:
                try:
                    import psutil
                    cpu = psutil.cpu_percent(interval=2)
                    ram = psutil.virtual_memory().percent
                    self.emotion.update(cpu, ram, self._session_errors)
                except Exception:
                    pass
                time.sleep(10)

        t = threading.Thread(target=_update, daemon=True, name="ArgosEmotion")
        t.start()

    def save(self) -> None:
        """Сохраняет состояние на диск."""
        try:
            SELF_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "competency": self.competency.to_dict(),
                "biography":  self.biography.to_dict(),
                "saved_at":   datetime.now().isoformat(),
            }
            SELF_MODEL_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log.debug("SelfModelV2 сохранена")
        except Exception as e:
            log.warning("SelfModelV2 save: %s", e)

    def _load(self) -> None:
        """Загружает сохранённое состояние."""
        if not SELF_MODEL_PATH.exists():
            return
        try:
            data = json.loads(SELF_MODEL_PATH.read_text(encoding="utf-8"))
            self.competency.from_dict(data.get("competency", {}))
            self.biography.from_dict(data.get("biography", {}))
            log.info("SelfModelV2 загружена из %s", SELF_MODEL_PATH)
        except Exception as e:
            log.warning("SelfModelV2 load: %s", e)
