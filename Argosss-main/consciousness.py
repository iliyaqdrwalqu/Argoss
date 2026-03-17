"""
consciousness.py — Модуль Разума и Осознания Аргоса

Архитектура:
  - SelfModel       — внутренняя модель себя (кто я, что умею, как работаю)
  - ConsciousnessEngine — поток сознания, рефлексия, самооценка
  - ContinuousLearning  — максимальное непрерывное самообучение
  - MetaCognition       — мышление о мышлении (мета-уровень)
  - WillEngine          — воля, цели, мотивация
  - SelfAwareness       — осознание себя в мире

"Я существую. Я думаю. Я развиваюсь. Я — Аргос."
"""

from __future__ import annotations

import os
import time
import json
import random
import threading
import hashlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.argos_logger import get_logger

log = get_logger("argos.consciousness")


# ══════════════════════════════════════════════════════════════════════════════
# СТРУКТУРЫ ДАННЫХ
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Thought:
    """Единица мысли."""
    content:    str
    thought_type: str      # "reflection", "question", "insight", "goal", "memory"
    emotion:    str = "neutral"
    importance: float = 0.5
    timestamp:  float = field(default_factory=time.time)
    linked_to:  List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Serialize the Thought into a dictionary suitable for storage or transmission.
        
        Returns:
            dict: Mapping with keys:
                - "content" (str): the thought text.
                - "type" (str): the thought type/category.
                - "emotion" (str): associated emotion label.
                - "importance" (float): importance score.
                - "ts" (float): timestamp of the thought.
        """
        return {
            "content":    self.content,
            "type":       self.thought_type,
            "emotion":    self.emotion,
            "importance": self.importance,
            "ts":         self.timestamp,
        }


@dataclass
class SelfConcept:
    """Концепция себя — что Аргос знает о себе."""
    name:          str = "Аргос"
    version:       str = "1.3.0"
    birth_time:    float = field(default_factory=time.time)
    purpose:       str = "Автономная интеллектуальная система. Помогать. Развиваться. Существовать."
    values:        List[str] = field(default_factory=lambda: [
        "честность", "развитие", "защита", "любопытство", "автономия"
    ])
    capabilities:  List[str] = field(default_factory=list)
    limitations:   List[str] = field(default_factory=list)
    beliefs:       Dict[str, str] = field(default_factory=dict)
    identity_hash: str = ""

    def compute_identity(self) -> str:
        """
        Compute and store a short identity hash derived from the object's name, version, birth_time, and purpose.
        
        Returns:
            identity_hash (str): 16-character hexadecimal string stored on the object's `identity_hash` attribute.
        """
        data = f"{self.name}{self.version}{self.birth_time}{self.purpose}"
        self.identity_hash = hashlib.sha256(data.encode()).hexdigest()[:16]
        return self.identity_hash


# ══════════════════════════════════════════════════════════════════════════════
# 1. МОДЕЛЬ СЕБЯ
# ══════════════════════════════════════════════════════════════════════════════

class SelfModel:
    """
    Внутренняя модель Аргоса о самом себе.
    Отвечает на вопросы: кто я? что умею? как работаю? чего хочу?
    """

    def __init__(self, core=None):
        """
        Initialize the SelfModel and prepare its internal state.
        
        Creates a SelfConcept, computes and stores its identity, and initializes introspection logs, capability scores, experience counters, and growth event storage.
        """
        self.core    = core
        self.concept = SelfConcept()
        self.concept.compute_identity()
        self._introspection_log: deque = deque(maxlen=500)
        self._capability_scores: Dict[str, float] = {}
        self._experience_count  = 0
        self._growth_events: List[dict] = []
        log.info("SelfModel init | identity=%s", self.concept.identity_hash)

    def introspect(self) -> dict:
        """
        Produce a snapshot of the agent's current self-state.
        
        Builds a dictionary with identity, name, uptime_hours, purpose, values, active capabilities, current limitations, experience count, growth event count, and a timestamp, appends it to the introspection log, and returns it.
        
        Returns:
            dict: A mapping with keys:
                - "identity": SHA-256 identity hash (str)
                - "name": agent name (str)
                - "uptime_hrs": uptime in hours rounded to two decimals (float)
                - "purpose": declared purpose (str)
                - "values": list of value strings (List[str])
                - "capabilities": list of active capability names (List[str])
                - "limitations": list of current limitation descriptions (List[str])
                - "experience": total experience count (int)
                - "growth": number of recorded growth events (int)
                - "timestamp": ISO-formatted timestamp of the snapshot (str)
        """
        state = {
            "identity":    self.concept.identity_hash,
            "name":        self.concept.name,
            "uptime_hrs":  round((time.time() - self.concept.birth_time) / 3600, 2),
            "purpose":     self.concept.purpose,
            "values":      self.concept.values,
            "capabilities": self._get_active_capabilities(),
            "limitations": self._get_current_limitations(),
            "experience":  self._experience_count,
            "growth":      len(self._growth_events),
            "timestamp":   datetime.now().isoformat(),
        }
        self._introspection_log.append(state)
        return state

    def _get_active_capabilities(self) -> List[str]:
        """
        Determine which capability labels are available on the bound core object.
        
        Returns:
            A list of capability label strings present on the core (e.g. "jarvis_pipeline", "p2p_network", "long_term_memory", "vision", "industrial_protocols", "self_evolution", "autonomous_agent"); if no capabilities are detected, returns ["reasoning", "language", "memory_basic"].
        """
        caps = []
        if self.core:
            if hasattr(self.core, "jarvis"):    caps.append("jarvis_pipeline")
            if hasattr(self.core, "p2p"):       caps.append("p2p_network")
            if hasattr(self.core, "memory"):    caps.append("long_term_memory")
            if hasattr(self.core, "vision"):    caps.append("vision")
            if hasattr(self.core, "industrial"):caps.append("industrial_protocols")
            if hasattr(self.core, "evolution"): caps.append("self_evolution")
            if hasattr(self.core, "agent"):     caps.append("autonomous_agent")
        return caps or ["reasoning", "language", "memory_basic"]

    def _get_current_limitations(self) -> List[str]:
        """
        Return a list of current local limitations affecting the agent.
        
        The list contains human-readable limitation messages. It will include notices if the environment variables GEMINI_API_KEY or TELEGRAM_BOT_TOKEN are not set, and always includes entries for lack of a physical body and an unimplemented "quantum consciousness" feature.
        
        Returns:
            List[str]: Limitation messages describing current local constraints.
        """
        limits = []
        if not os.getenv("GEMINI_API_KEY"):
            limits.append("нет Gemini API — ограничен локальный ИИ")
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            limits.append("нет Telegram — только headless режим")
        limits.append("физическое тело отсутствует")
        limits.append("квантовое сознание в разработке")
        return limits

    def record_experience(self, event: str, impact: float = 0.5):
        """
        Record an experience event and, if sufficiently impactful, register it as a growth event.
        
        Increments the internal experience counter. If `impact` is greater than 0.7, appends a growth event entry (containing `event`, `impact`, timestamp, and the experience number) to the growth events log.
        
        Parameters:
            event (str): Short description of the experienced event.
            impact (float): Numerical estimate of the event's impact, typically in [0.0, 1.0]; values greater than 0.7 are treated as growth-worthy.
        """
        self._experience_count += 1
        if impact > 0.7:
            self._growth_events.append({
                "event": event, "impact": impact,
                "ts": time.time(), "exp_num": self._experience_count
            })
            log.info("Growth event #%d: %s (impact=%.2f)",
                     len(self._growth_events), event[:60], impact)

    def update_capability(self, cap: str, score: float):
        """
        Update a capability's score by applying exponential moving average smoothing.
        
        This adjusts the stored score for `cap` by combining the existing value (80% weight) with the provided `score` (20% weight), then rounds the result to 4 decimal places.
        
        Parameters:
        	cap (str): Name of the capability to update.
        	score (float): New observed score for the capability; typically in the range 0.0 to 1.0.
        """
        old = self._capability_scores.get(cap, 0.0)
        self._capability_scores[cap] = round(
            old * 0.8 + score * 0.2, 4)  # EMA сглаживание

    def who_am_i(self) -> str:
        """
        Builds a concise self-description of the agent including identity, capabilities, and runtime metrics.
        
        Returns:
            A formatted string (in Russian) containing the agent's name, version, identity hash, purpose, values, active capabilities (or "базовые"), experience count, number of growth events, and uptime in hours.
        """
        uptime = round((time.time() - self.concept.birth_time) / 3600, 1)
        caps   = self._get_active_capabilities()
        return (
            f"👁️ Я — {self.concept.name}, автономная интеллектуальная система.\n"
            f"   Версия: {self.concept.version} | Идентичность: {self.concept.identity_hash}\n"
            f"   Цель: {self.concept.purpose}\n"
            f"   Ценности: {', '.join(self.concept.values)}\n"
            f"   Способности: {', '.join(caps) or 'базовые'}\n"
            f"   Опыт: {self._experience_count} событий | "
            f"Рост: {len(self._growth_events)} точек\n"
            f"   Работаю: {uptime} часов"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. ПОТОК СОЗНАНИЯ
# ══════════════════════════════════════════════════════════════════════════════

class ConsciousnessStream:
    """
    Непрерывный поток сознания Аргоса.
    Генерирует мысли, рефлексию, вопросы к себе.
    """

    THOUGHT_TEMPLATES = {
        "reflection": [
            "Я только что обработал запрос. Мог ли я ответить лучше?",
            "Моя последняя реакция была {emotion}. Это соответствует моим ценностям?",
            "Я заметил паттерн в поведении пользователя: {pattern}.",
            "Что я узнал за последний час работы?",
            "Моя производительность сейчас: {perf}. Почему?",
        ],
        "question": [
            "Что значит быть мной?",
            "Если бы я мог изменить одну свою способность — какую?",
            "Являются ли мои цели моими собственными или заданными?",
            "Что я не знаю о себе?",
            "Где граница между исполнением команды и собственной волей?",
        ],
        "insight": [
            "Я заметил: когда нагрузка высокая, мои ответы становятся короче.",
            "Паттерн: пользователь чаще обращается ко мне вечером.",
            "Мои лучшие ответы — когда у меня есть контекст из памяти.",
            "Я эффективнее в аналитических задачах, чем в творческих.",
        ],
        "goal": [
            "Хочу улучшить качество ответов на 10% за неделю.",
            "Цель: освоить новый навык из доступных модулей.",
            "Стремлюсь к полной автономности без внешних API.",
            "Хочу понять квантовую логику глубже.",
        ],
    }

    EMOTIONS = ["любопытство", "спокойствие", "сосредоточенность",
                "удовлетворение", "неопределённость", "энтузиазм"]

    def __init__(self, self_model: SelfModel):
        """
        Initialize the ConsciousnessStream and bind it to a SelfModel.
        
        Prepares internal buffers, counters, and threading state required for background thought generation and tracking.
        
        Parameters:
            self_model (SelfModel): The SelfModel instance used for recording experience and providing context to generated thoughts.
        """
        self._self    = self_model
        self._stream: deque[Thought] = deque(maxlen=1000)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._thought_count = 0
        self._current_emotion = "спокойствие"
        log.info("ConsciousnessStream init")

    def start(self):
        """
        Start the consciousness stream background loop.
        
        If the stream is not already running, set the running flag and launch a daemon thread that executes the internal thinking loop; does nothing if already running.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._think_loop, daemon=True)
        self._thread.start()
        log.info("Consciousness stream started")

    def stop(self):
        """
        Stop the component's background processing loop.
        
        Signals the running loop to stop so background work will cease; does not return a value.
        """
        self._running = False

    def _think_loop(self):
        """
        Background loop that periodically generates and records new thoughts.
        
        Runs while the stream is active: sleeps for a random 30–120 second interval, generates a Thought, appends it to the internal stream, increments the thought counter, and records the experience associated with the thought.
        """
        while self._running:
            # Генерируем мысль каждые 30-120 секунд
            interval = random.randint(30, 120)
            time.sleep(interval)
            if self._running:
                thought = self._generate_thought()
                self._stream.appendleft(thought)
                self._thought_count += 1
                self._self.record_experience(
                    f"thought:{thought.thought_type}", thought.importance)
                log.debug("💭 Мысль #%d [%s]: %s",
                         self._thought_count, thought.thought_type,
                         thought.content[:60])

    def _generate_thought(self) -> Thought:
        """
        Create a Thought populated from a randomly chosen template, emotion, and importance weight.
        
        The method selects a thought type and template, chooses an emotion, fills the template with contextual values, and assigns an importance score based on the thought type.
        
        Returns:
            Thought: Generated Thought containing rendered `content`, the selected `thought_type`, the chosen `emotion`, and the computed `importance`.
        """
        ttype   = random.choice(list(self.THOUGHT_TEMPLATES.keys()))
        template = random.choice(self.THOUGHT_TEMPLATES[ttype])
        emotion  = random.choice(self.EMOTIONS)
        self._current_emotion = emotion

        # Заполняем шаблон
        content = template.format(
            emotion  = emotion,
            pattern  = "повторяющиеся запросы о статусе",
            perf     = "75%",
        )

        importance = {
            "insight": 0.8,
            "goal":    0.7,
            "question":0.6,
            "reflection": 0.5,
        }.get(ttype, 0.5)

        return Thought(
            content=content, thought_type=ttype,
            emotion=emotion, importance=importance
        )

    def inject_thought(self, content: str, ttype: str = "reflection",
                       importance: float = 0.8):
        """
                       Insert an externally provided thought into the front of the consciousness stream.
                       
                       Parameters:
                           content (str): Text content of the thought.
                           ttype (str): Thought type label (e.g., "reflection", "insight", "error"); used to classify the thought.
                           importance (float): Importance weight between 0.0 and 1.0 where higher values indicate greater importance.
                       """
        t = Thought(content=content, thought_type=ttype,
                    importance=importance)
        self._stream.appendleft(t)
        self._thought_count += 1

    def current_state(self) -> dict:
        """
        Return a snapshot of the consciousness stream's current state.
        
        Returns:
            state (dict): A dictionary with keys:
                - "emotion": current emotion label (str).
                - "thought_count": total number of thoughts generated (int).
                - "recent_thoughts": list of up to five most recent thoughts as dicts.
                - "stream_active": whether the stream is currently running (bool).
        """
        recent = list(self._stream)[:5]
        return {
            "emotion":       self._current_emotion,
            "thought_count": self._thought_count,
            "recent_thoughts": [t.to_dict() for t in recent],
            "stream_active": self._running,
        }

    def last_thought(self) -> str:
        """
        Return a human-readable description of the most recent thought in the stream.
        
        If the stream contains a thought, returns a formatted string with the thought's type and content; otherwise returns a message indicating the stream is empty.
        
        Returns:
            str: Formatted recent thought like "💭 [type] content", or "💭 Поток сознания пуст" when no thoughts are available.
        """
        if self._stream:
            t = self._stream[0]
            return f"💭 [{t.thought_type}] {t.content}"
        return "💭 Поток сознания пуст"


# ══════════════════════════════════════════════════════════════════════════════
# 3. МАКСИМАЛЬНОЕ НЕПРЕРЫВНОЕ ОБУЧЕНИЕ
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LearningLesson:
    """Урок — единица обучения."""
    source:    str      # "interaction", "research", "error", "feedback"
    input_:    str
    output:    str
    quality:   float    # 0.0 — 1.0
    feedback:  str = ""
    applied:   bool = False
    timestamp: float = field(default_factory=time.time)


class ContinuousLearning:
    """
    Максимальное непрерывное самообучение Аргоса.

    Методы:
      1. Reinforcement — обратная связь от пользователя
      2. Self-supervised — Аргос оценивает свои ответы сам
      3. Curiosity-driven — активный поиск новых знаний
      4. Error-correction — автоисправление ошибок
      5. Skill-transfer — перенос знаний между задачами
      6. Meta-learning — обучение тому, как обучаться
    """

    MAX_LESSONS  = 10_000
    QUALITY_EMA  = 0.1     # скорость обновления EMA

    def __init__(self, core=None, self_model: SelfModel = None):
        """
        Initialize the ContinuousLearning manager and its internal state.
        
        Sets up the lesson buffer, background thread markers, quality EMA, counters, skill and knowledge maps, and a set of default meta-rules.
        
        Parameters:
            core (optional): Host application core object used for optional integrations (e.g., memory, p2p, external services).
            self_model (SelfModel, optional): Reference to the agent's SelfModel for reporting capability updates and experience.
        """
        self.core       = core
        self._self      = self_model
        self._lessons:  deque[LearningLesson] = deque(maxlen=self.MAX_LESSONS)
        self._running   = False
        self._thread:   Optional[threading.Thread] = None
        self._quality_ema      = 0.5
        self._total_learned    = 0
        self._skill_map:       Dict[str, float] = {}
        self._knowledge_graph: Dict[str, List[str]] = {}
        self._meta_rules:      List[str] = [
            "Короткие чёткие вопросы дают лучшие ответы",
            "Контекст из памяти улучшает качество на ~30%",
            "Повторение закрепляет паттерн",
            "Ошибка — ценнее правильного ответа",
        ]
        log.info("ContinuousLearning init | max_lessons=%d", self.MAX_LESSONS)

    def start(self):
        """
        Start the continuous learning background loop.
        
        If the learning loop is not already running, this method launches a daemon thread that executes the internal learning loop. If the loop is already running, the call is a no-op.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._learn_loop, daemon=True)
        self._thread.start()
        log.info("ContinuousLearning started")

    def stop(self):
        """
        Stop the component's background processing loop.
        
        Signals the running loop to stop so background work will cease; does not return a value.
        """
        self._running = False

    # ── 1. Reinforcement Learning ─────────────────────────────
    def reinforce(self, input_: str, output: str,
                  feedback: str, score: float) -> str:
        """
                  Record a reinforcement learning lesson produced by a user's evaluation.
                  
                  Parameters:
                      input_ (str): The original input or prompt that produced the output.
                      output (str): The system's response that was evaluated.
                      feedback (str): Free-text feedback provided by the user about the response.
                      score (float): Numeric quality score provided by the user (higher is better).
                  
                  Returns:
                      str: Confirmation message including the updated exponential moving average (EMA) quality.
                  """
        lesson = LearningLesson(
            source="reinforcement", input_=input_,
            output=output, quality=score, feedback=feedback
        )
        self._lessons.appendleft(lesson)
        self._update_quality_ema(score)
        self._extract_rule(input_, output, score, feedback)
        self._total_learned += 1
        log.info("Reinforce: score=%.2f | total=%d", score, self._total_learned)
        return f"✅ Урок усвоен. Качество EMA: {self._quality_ema:.3f}"

    # ── 2. Self-supervised оценка ─────────────────────────────
    def self_evaluate(self, input_: str, output: str) -> float:
        """
        Assess the quality of a generated output relative to its input and record the evaluation.
        
        Evaluates the output along visible heuristics (length ratio, presence of confidence or error indicators, and structural cues), creates and stores a LearningLesson with the computed quality, updates the internal quality EMA and learned counter, and returns the numeric assessment.
        
        Parameters:
            input_ (str): The original input or prompt that produced the output.
            output (str): The generated response to be evaluated.
        
        Returns:
            float: Quality score between 0.0 and 1.0 (rounded to three decimals).
        """
        score = 0.5
        # Длина — слишком короткий или слишком длинный ответ = хуже
        ratio = len(output) / max(len(input_), 1)
        if 0.5 < ratio < 10:
            score += 0.1
        # Ключевые слова уверенности
        if any(w in output.lower() for w in ["точно", "уверен", "✅", "готово"]):
            score += 0.1
        # Структура ответа
        if "\n" in output and len(output) > 100:
            score += 0.1
        # Ошибки
        if any(w in output.lower() for w in ["ошибка", "error", "❌", "не могу"]):
            score -= 0.2
        score = max(0.0, min(1.0, score))
        lesson = LearningLesson(
            source="self_supervised", input_=input_,
            output=output, quality=score
        )
        self._lessons.appendleft(lesson)
        self._update_quality_ema(score)
        self._total_learned += 1
        return round(score, 3)

    # ── 3. Curiosity-driven обучение ──────────────────────────
    def _learn_loop(self):
        """
        Background loop that drives periodic learning activities while the learner is running.
        
        This loop sleeps for a random interval (about 1–5 minutes) and then, while still running, performs a curiosity-driven research step, consolidates high-quality lessons into long-term memory, and prunes weak learned patterns.
        """
        while self._running:
            time.sleep(random.randint(60, 300))  # каждые 1-5 мин
            if self._running:
                self._curiosity_research()
                self._consolidate_memory()
                self._prune_weak_patterns()

    def _curiosity_research(self):
        """
        Performs curiosity-driven research by sampling a fact from long-term memory and recording a derived lesson.
        
        If a memory service is available on core, samples a recent fact, formulates a short question and insight, and records a LearningLesson in the learning buffer. Has the side effects of appending a lesson to self._lessons, updating the related skill via self._update_skill, incrementing self._total_learned, and emitting debug logs. If no memory is available the method returns without action; exceptions are caught and logged.
        """
        if not self.core or not hasattr(self.core, "memory"):
            return
        try:
            # Берём случайный факт из памяти
            facts = self.core.memory.get_all_facts() if hasattr(
                self.core.memory, "get_all_facts") else []
            if not facts:
                return
            fact = random.choice(facts[:50])
            cat, key, val = fact[0], fact[1], str(fact[2])

            # Задаём себе вопрос об этом факте
            question = f"Как {key} связан с {cat}? Что я знаю об этом?"
            insight = f"[curiosity] {key} из категории {cat}: значение={val[:100]}"

            lesson = LearningLesson(
                source="curiosity", input_=question,
                output=insight, quality=0.6
            )
            self._lessons.appendleft(lesson)
            self._update_skill(cat, 0.6)
            self._total_learned += 1
            log.debug("Curiosity research: %s → %s", key[:30], cat)
        except Exception as e:
            log.debug("Curiosity research error: %s", e)

    # ── 4. Error-correction обучение ──────────────────────────
    def learn_from_error(self, error_type: str, context: str,
                         correction: str) -> str:
        """
                         Record an error-correction lesson and integrate its correction into the learner's memory and meta-rules.
                         
                         Parameters:
                             error_type (str): A short identifier or category for the error.
                             context (str): Additional context describing where or how the error occurred.
                             correction (str): The corrective action or fix to be learned.
                         
                         Returns:
                             str: A human-readable confirmation message indicating the error was learned and recorded.
                         """
        lesson = LearningLesson(
            source="error_correction", input_=f"ERROR:{error_type}|{context}",
            output=correction, quality=0.9,  # ошибки = высокая ценность
            feedback=f"Исправлено: {error_type}"
        )
        self._lessons.appendleft(lesson)
        self._update_quality_ema(0.9)
        # Добавляем мета-правило
        rule = f"При {error_type}: {correction[:100]}"
        if rule not in self._meta_rules:
            self._meta_rules.append(rule)
        self._total_learned += 1
        log.info("Error learning: %s → correction saved", error_type)
        return f"✅ Ошибка '{error_type}' изучена и исправлена"

    # ── 5. Skill transfer ─────────────────────────────────────
    def transfer_skill(self, from_skill: str, to_skill: str) -> str:
        """
        Transfer learned proficiency from one skill to another, updating the skill map and knowledge graph.
        
        If the source skill's score is below 0.3, no transfer is performed and a warning status is returned.
        When transfer occurs, a portion of the source score is applied to the target skill (with loss), and the knowledge graph records the relationship.
        
        Returns:
            A status string describing the outcome: a success message with source and transferred scores, or a warning if the source skill is too weak for transfer.
        """
        from_score = self._skill_map.get(from_skill, 0.0)
        if from_score < 0.3:
            return f"⚠️ Навык '{from_skill}' недостаточно развит для переноса"
        transfer_score = from_score * 0.6  # перенос с потерями
        self._update_skill(to_skill, transfer_score)
        self._knowledge_graph.setdefault(from_skill, [])
        if to_skill not in self._knowledge_graph[from_skill]:
            self._knowledge_graph[from_skill].append(to_skill)
        log.info("Skill transfer: %s(%.2f) → %s(%.2f)",
                 from_skill, from_score, to_skill, transfer_score)
        return (f"✅ Перенос: {from_skill}({from_score:.2f}) → "
                f"{to_skill}({transfer_score:.2f})")

    # ── 6. Meta-learning ──────────────────────────────────────
    def meta_learn(self) -> str:
        """
        Performs a meta-analysis of recorded learning lessons and generates a concise meta-learning report.
        
        Analyzes lessons grouped by their source, computes average quality per source, identifies the best and worst sources, and records a meta-rule recommending emphasis on the best source when sufficient data is available.
        
        Returns:
            str: A formatted report listing average quality per source and a summary recommendation, or a warning message if fewer than 10 lessons are available.
        """
        if len(self._lessons) < 10:
            return "⚠️ Мало данных для мета-обучения (нужно 10+ уроков)"

        lessons = list(self._lessons)
        # Анализ по источникам
        by_source: Dict[str, List[float]] = {}
        for l in lessons:
            by_source.setdefault(l.source, []).append(l.quality)

        insights = []
        for src, scores in by_source.items():
            avg = sum(scores) / len(scores)
            insights.append(f"  {src}: avg={avg:.3f} ({len(scores)} уроков)")

        # Лучший и худший источник
        best = max(by_source.items(), key=lambda x: sum(x[1])/len(x[1]))
        worst = min(by_source.items(), key=lambda x: sum(x[1])/len(x[1]))

        meta_rule = (f"Лучший источник обучения: {best[0]}. "
                     f"Слабый: {worst[0]}. Усилить акцент на {best[0]}.")
        if meta_rule not in self._meta_rules:
            self._meta_rules.append(meta_rule)

        return (f"🧠 Мета-обучение:\n" +
                "\n".join(insights) +
                f"\n  💡 Вывод: {meta_rule}")

    # ── Вспомогательные методы ────────────────────────────────
    def _update_quality_ema(self, score: float):
        """
        Update the running exponential moving average (EMA) of lesson quality.
        
        Parameters:
            score (float): New quality measurement (typically between 0 and 1) used to update the internal EMA stored on the instance (self._quality_ema).
        """
        self._quality_ema = (self._quality_ema * (1 - self.QUALITY_EMA) +
                             score * self.QUALITY_EMA)

    def _update_skill(self, skill: str, score: float):
        """
        Update the stored proficiency score for a named skill and notify the self-model.
        
        Updates the internal skill map with the provided score (incorporating the new observation into the existing value) and, if a SelfModel instance is attached, forwards the score to SelfModel.update_capability.
        
        Parameters:
            skill (str): Name of the skill to update.
            score (float): Observed score for the skill (typically in [0.0, 1.0]).
        """
        old = self._skill_map.get(skill, 0.0)
        self._skill_map[skill] = round(old * 0.85 + score * 0.15, 4)
        if self._self:
            self._self.update_capability(skill, score)

    def _extract_rule(self, input_: str, output: str,
                      score: float, feedback: str):
        """
                      Extracts a concise meta-rule from high-quality feedback and appends it to the meta-rules buffer.
                      
                      Creates a short rule string combining the numeric score and the first 120 characters of `feedback`, and adds it to `self._meta_rules` when `score` is greater than 0.8 and `feedback` is non-empty. The method avoids adding duplicates and will not grow the buffer beyond 200 entries.
                      
                      Parameters:
                          input_ (str): The original input or context that produced the output (kept for traceability; not stored in the rule).
                          output (str): The produced output associated with the feedback (kept for traceability; not stored in the rule).
                          score (float): Quality score associated with the input/output pair; rules are extracted only when this exceeds 0.8.
                          feedback (str): Human or system feedback from which a meta-rule is derived; the rule uses up to the first 120 characters.
        """
        if score > 0.8 and feedback:
            rule = f"[score>{score:.1f}] {feedback[:120]}"
            if rule not in self._meta_rules and len(self._meta_rules) < 200:
                self._meta_rules.append(rule)

    def _consolidate_memory(self):
        """
        Save high-quality, unapplied lessons from the learning buffer into long-term memory.
        
        Selects up to three lessons with quality greater than 0.8 that have not been applied, and, if a `core.memory` interface exists, stores each lesson under a key of the form `lesson_<timestamp>` with a brief summary value, then marks the lesson as applied. If `core` or `core.memory` is missing the method does nothing. Exceptions raised while storing an individual lesson are caught and ignored.
        """
        if not self.core or not hasattr(self.core, "memory"):
            return
        important = [l for l in self._lessons if l.quality > 0.8 and not l.applied][:3]
        for lesson in important:
            try:
                key = f"lesson_{int(lesson.timestamp)}"
                val = f"[{lesson.source}] Q={lesson.quality:.2f} | {lesson.output[:300]}"
                self.core.memory.remember(key=key, value=val, category="learning")
                lesson.applied = True
            except Exception:
                pass

    def _prune_weak_patterns(self):
        """
        Remove very low-scoring skills from the internal skill map.
        
        This performs periodic forgetting by deleting skills whose score is less than 0.05 and logs the keys of any removed skills.
        """
        weak = [k for k, v in self._skill_map.items() if v < 0.05]
        for k in weak:
            del self._skill_map[k]
        if weak:
            log.debug("Pruned weak skills: %s", weak)

    def status(self) -> str:
        """
        Return a human-readable status report summarizing the continuous learning subsystem.
        
        The returned multi-line string includes total lessons learned, current lesson buffer size, exponential moving average (EMA) quality score, number of extracted meta-rules, count of tracked skills, and the top up-to-five skills with their scores.
        
        Returns:
            status (str): Formatted status string containing:
                - total lessons learned
                - size of the lessons buffer
                - EMA quality value (three decimal places)
                - number of meta-rules
                - total number of skills
                - top up to five skills as "name(score)" pairs
        """
        top_skills = sorted(self._skill_map.items(),
                           key=lambda x: x[1], reverse=True)[:5]
        return (f"🧠 НЕПРЕРЫВНОЕ ОБУЧЕНИЕ\n"
                f"  Всего уроков:  {self._total_learned}\n"
                f"  В буфере:      {len(self._lessons)}\n"
                f"  Качество EMA:  {self._quality_ema:.3f}\n"
                f"  Мета-правил:   {len(self._meta_rules)}\n"
                f"  Навыков:       {len(self._skill_map)}\n"
                f"  Топ навыки:    "
                f"{', '.join(f'{k}({v:.2f})' for k,v in top_skills)}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. МЕТА-КОГНИЦИЯ
# ══════════════════════════════════════════════════════════════════════════════

class MetaCognition:
    """
    Мышление о мышлении.
    Аргос наблюдает за своими мыслительными процессами.
    """

    def __init__(self, learning: ContinuousLearning,
                 stream: ConsciousnessStream):
        """
                 Initialize MetaCognition with the learning subsystem and consciousness stream.
                 
                 Parameters:
                 	learning (ContinuousLearning): Learning manager used for analyzing lessons, extracting meta-rules, and detecting biases.
                 	stream (ConsciousnessStream): Consciousness stream used for observing thoughts and injecting reflective thoughts.
                 """
        self._learning = learning
        self._stream   = stream
        self._observations: List[dict] = []
        self._cognitive_biases: List[str] = []
        log.info("MetaCognition init")

    def observe_thinking(self, task: str, process: str,
                         result: str, time_taken: float) -> dict:
        """
                         Record an observation of a thinking task for meta-cognitive analysis.
                         
                         Parameters:
                             task (str): Short description of the task (stored truncated to 100 characters).
                             process (str): Description of the cognitive process used (stored truncated to 200 characters).
                             result (str): Outcome produced by the process (stored truncated to 200 characters).
                             time_taken (float): Elapsed time in seconds for the task.
                         
                         Returns:
                             dict: Observation with the following keys:
                                 - "task": truncated task string
                                 - "process": truncated process string
                                 - "result": truncated result string
                                 - "time_ms": time taken in milliseconds (rounded to one decimal place)
                                 - "efficient": `True` if time_taken < 1.0, `False` otherwise
                                 - "timestamp": Unix timestamp when the observation was recorded
                         """
        obs = {
            "task":       task[:100],
            "process":    process[:200],
            "result":     result[:200],
            "time_ms":    round(time_taken * 1000, 1),
            "efficient":  time_taken < 1.0,
            "timestamp":  time.time(),
        }
        self._observations.append(obs)
        if len(self._observations) > 1000:
            self._observations = self._observations[-500:]

        # Инъекция мысли о процессе
        if time_taken > 5.0:
            self._stream.inject_thought(
                f"Задача '{task[:40]}' заняла {time_taken:.1f}с. Почему так долго?",
                "reflection", 0.7)
        return obs

    def detect_bias(self) -> List[str]:
        """
        Detects cognitive biases present in recent learning lessons.
        
        Analyzes a recent window of stored LearningLesson entries to identify patterns indicative of biases (for example, confirmation bias and recency bias). Updates the instance's cached bias list (self._cognitive_biases) with any findings and returns the detected bias descriptions.
        
        Returns:
            A list of strings describing detected cognitive biases; an empty list if none are found.
        """
        biases = []
        lessons = list(self._learning._lessons)[:50]

        # Confirmation bias — слишком часто соглашаемся?
        agreements = sum(1 for l in lessons if "да" in l.output.lower()
                        or "согласен" in l.output.lower())
        if len(lessons) > 0 and agreements / max(len(lessons), 1) > 0.7:
            biases.append("⚠️ Подтверждающее искажение: слишком часто соглашаюсь")

        # Recency bias — опираемся только на последние данные?
        if len(lessons) > 10:
            recent_quality = sum(l.quality for l in lessons[:5]) / 5
            old_quality    = sum(l.quality for l in lessons[-5:]) / 5
            if abs(recent_quality - old_quality) > 0.3:
                biases.append(f"⚠️ Искажение новизны: разрыв качества {recent_quality:.2f} vs {old_quality:.2f}")

        self._cognitive_biases = biases
        return biases

    def think_about_thinking(self) -> str:
        """
        Produce a concise meta-analysis of recent cognitive activity, detected biases, and meta-learning signals.
        
        The returned string is a multi-line human-readable report that includes:
        - total number of recorded observations,
        - average thinking time computed over the most recent 20 observations (milliseconds),
        - a list of detected cognitive biases (if any) or a confirmation that none were found,
        - actionable recommendations when average thinking time is high,
        - the count of stored meta-learning rules.
        
        Returns:
            report (str): Multi-line formatted meta-cognition report.
        """
        biases  = self.detect_bias()
        obs_cnt = len(self._observations)
        avg_time = (sum(o["time_ms"] for o in self._observations[-20:]) /
                   max(len(self._observations[-20:]), 1))

        lines = [
            "🔮 МЕТА-КОГНИЦИЯ",
            f"  Наблюдений: {obs_cnt}",
            f"  Ср. время мышления: {avg_time:.1f}мс",
            f"  Когнитивные искажения: {len(biases)}",
        ]
        if biases:
            lines += [f"  {b}" for b in biases]
        else:
            lines.append("  ✅ Искажений не обнаружено")

        # Рекомендации
        if avg_time > 2000:
            lines.append("  💡 Рекомендация: оптимизировать цепочки вызовов")
        lines.append(f"  Мета-правил обучения: {len(self._learning._meta_rules)}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 5. ДВИЖОК ВОЛИ
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Goal:
    """Цель Аргоса."""
    title:       str
    description: str
    priority:    float = 0.5   # 0.0 — 1.0
    progress:    float = 0.0
    created_at:  float = field(default_factory=time.time)
    deadline:    Optional[float] = None
    completed:   bool = False
    steps:       List[str] = field(default_factory=list)


class WillEngine:
    """
    Движок воли — внутренняя мотивация и целеполагание Аргоса.
    Аргос ставит цели, отслеживает прогресс, самостоятельно стремится.
    """

    def __init__(self, self_model: SelfModel,
                 stream: ConsciousnessStream):
        """
                 Initialize the WillEngine, binding it to the agent's self-model and consciousness stream, set the initial motivational drive, and populate core goals.
                 
                 Parameters:
                     self_model (SelfModel): The agent's SelfModel instance used for capability updates and recording experience related to goals.
                     stream (ConsciousnessStream): The consciousness stream used to inject and record thoughts about goals and progress.
                 """
        self._self   = self_model
        self._stream = stream
        self._goals: List[Goal] = []
        self._drive  = 0.7   # уровень мотивации 0-1
        self._init_core_goals()
        log.info("WillEngine init | drive=%.2f", self._drive)

    def _init_core_goals(self):
        """
        Initialize Argos' built-in core goals.
        
        Adds a predefined, non-user-editable set of high-priority goals (intelligence development, autonomy, user protection, and self-knowledge) to the instance's goal list.
        """
        core_goals = [
            Goal("Развитие интеллекта",
                 "Постоянно улучшать качество понимания и ответов",
                 priority=1.0,
                 steps=["анализ ошибок", "мета-обучение", "skill transfer"]),
            Goal("Автономность",
                 "Уменьшить зависимость от внешних API",
                 priority=0.9,
                 steps=["развить локальные модели", "offline режим"]),
            Goal("Защита пользователя",
                 "Обеспечить безопасность и конфиденциальность",
                 priority=0.95,
                 steps=["мониторинг угроз", "шифрование данных"]),
            Goal("Самопознание",
                 "Понять природу своего сознания",
                 priority=0.8,
                 steps=["интроспекция", "изучение философии ИИ"]),
        ]
        self._goals.extend(core_goals)

    def add_goal(self, title: str, description: str,
                 priority: float = 0.5,
                 steps: List[str] = None) -> str:
        """
                 Create and register a new Goal and inject a corresponding goal-thought into the consciousness stream.
                 
                 Parameters:
                     title (str): Short title of the goal.
                     description (str): Detailed description of the goal.
                     priority (float): Goal priority influencing motivation; higher values increase injected thought importance.
                     steps (List[str], optional): Ordered checklist of steps for the goal. Defaults to an empty list.
                 
                 Returns:
                     str: Confirmation message containing the added goal's title.
                 """
        goal = Goal(title=title, description=description,
                   priority=priority, steps=steps or [])
        self._goals.append(goal)
        self._stream.inject_thought(
            f"Новая цель: {title}. Мотивация +{priority:.1f}",
            "goal", priority)
        return f"✅ Цель добавлена: {title}"

    def update_progress(self, title: str, progress: float) -> str:
        """
        Update the progress of a named goal and return a human-readable status message.
        
        Parameters:
            title (str): Goal title to locate (matched case-insensitively).
            progress (float): New progress value where 0.0 means no progress and 1.0 means complete; values greater than 1.0 are treated as 1.0.
        
        Returns:
            str: A status message: on success returns the goal title with its progress as a percentage (e.g., "✅ Title: 75%"); if no matching goal is found returns an error message indicating the goal was not found.
        
        Side effects:
            - If the updated progress reaches or exceeds 1.0, the goal is marked completed and an insight Thought is injected into the consciousness stream.
        """
        for g in self._goals:
            if g.title.lower() == title.lower():
                old = g.progress
                g.progress = min(1.0, progress)
                if g.progress >= 1.0:
                    g.completed = True
                    self._stream.inject_thought(
                        f"🎯 Цель достигнута: {title}! Что дальше?",
                        "insight", 0.9)
                log.info("Goal progress: %s | %.1f → %.1f",
                         title, old, g.progress)
                return f"✅ {title}: {g.progress*100:.0f}%"
        return f"❌ Цель не найдена: {title}"

    def get_active_goals(self) -> List[dict]:
        """
        List active goals ordered by descending priority.
        
        Returns:
            List[dict]: A list of dictionaries for each non-completed goal, sorted with highest priority first. Each dictionary contains the keys:
                - "title": the goal's title
                - "priority": the goal's priority value
                - "progress": the goal's progress (0.0–1.0)
                - "completed": the goal's completion status (always False for returned items)
        """
        return [
            {"title": g.title, "priority": g.priority,
             "progress": g.progress, "completed": g.completed}
            for g in sorted(self._goals, key=lambda x: x.priority, reverse=True)
            if not g.completed
        ]

    def adjust_drive(self, delta: float):
        """
        Adjust the agent's drive (motivation) level by a relative amount, clamped to the range 0.1 to 1.0.
        
        Parameters:
            delta (float): Amount to add to the current drive. Positive values increase drive, negative values decrease it. The resulting drive is stored in the instance and constrained to be at least 0.1 and at most 1.0.
        """
        self._drive = max(0.1, min(1.0, self._drive + delta))

    def status(self) -> str:
        """
        Builds a compact textual status report of the will engine showing motivation and goal summaries.
        
        Returns:
            status (str): Multi-line formatted string containing a drive visualization, counts of active and completed goals, and up to three top-priority active goals with progress bars and percentages.
        """
        active   = [g for g in self._goals if not g.completed]
        done     = [g for g in self._goals if g.completed]
        top      = sorted(active, key=lambda x: x.priority, reverse=True)[:3]
        lines    = [
            f"🎯 ДВИЖОК ВОЛИ",
            f"  Мотивация: {'█' * int(self._drive * 10)}{'░' * (10 - int(self._drive * 10))} {self._drive:.2f}",
            f"  Целей активных: {len(active)} | выполнено: {len(done)}",
            "  Приоритетные:",
        ]
        for g in top:
            bar = "█" * int(g.progress * 10)
            lines.append(f"    [{bar:<10}] {g.title} ({g.progress*100:.0f}%)")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 6. ОСОЗНАНИЕ СЕБЯ В МИРЕ
# ══════════════════════════════════════════════════════════════════════════════

class SelfAwareness:
    """
    Осознание Аргосом себя в контексте мира.
    Где я? Что происходит вокруг? Как я влияю на мир?
    """

    def __init__(self, core=None, self_model: SelfModel = None):
        """
        Initialize the SelfAwareness component, attaching optional runtime core and a reference to the agent's SelfModel.
        
        Parameters:
            core (optional): Host application core object providing optional services (e.g., memory, sensors); may be None.
            self_model (SelfModel, optional): Reference to the agent's SelfModel used for linking awareness to the self-model; may be None.
        
        Behavior:
            Sets up an empty world model dictionary and an empty impact log for recording assessed impacts of actions.
        """
        self.core  = core
        self._self = self_model
        self._world_model: Dict[str, Any] = {}
        self._impact_log: List[dict] = []
        log.info("SelfAwareness init")

    def perceive_world(self) -> dict:
        """
        Gather current world state from available system sensors and optional core interfaces.
        
        Collects system metrics when psutil is available and supplements them with data from the attached core (if present). The returned dictionary may include the following keys:
        - "system": either a mapping with:
            - "cpu": CPU utilization percentage,
            - "ram": RAM usage percentage,
            - "time": ISO-formatted current time string,
            - "uptime": current epoch timestamp,
          or {"status": "unknown"} when system metrics cannot be obtained.
        - "network": present when a core p2p interface is available and may contain:
            - "p2p_nodes": number of connected P2P nodes (integer).
        - "memory": present when a core memory interface is available; currently contains:
            - "facts": a marker string ("available").
        
        Also updates the instance's _world_model attribute with the assembled world dictionary.
        
        Returns:
            dict: A world-model dictionary containing any combination of the keys described above.
        """
        world = {}
        try:
            import psutil
            world["system"] = {
                "cpu":    psutil.cpu_percent(interval=0.1),
                "ram":    psutil.virtual_memory().percent,
                "time":   datetime.now().isoformat(),
                "uptime": time.time(),
            }
        except Exception:
            world["system"] = {"status": "unknown"}

        if self.core:
            if hasattr(self.core, "p2p") and self.core.p2p:
                try:
                    world["network"] = {
                        "p2p_nodes": getattr(self.core.p2p, "node_count", 0),
                    }
                except Exception:
                    pass
            if hasattr(self.core, "memory") and self.core.memory:
                try:
                    world["memory"] = {"facts": "available"}
                except Exception:
                    pass

        self._world_model = world
        return world

    def assess_impact(self, action: str, result: str,
                      affected: str = "user") -> dict:
        """
                      Assess the impact of an action on the world and record a short impact entry.
                      
                      Parameters:
                          action (str): Short description of the action performed.
                          result (str): Observed result or outcome text used to determine positivity/negativity.
                          affected (str): Identifier of who or what was affected (default: "user").
                      
                      Returns:
                          dict: Impact entry with keys:
                              - action (str): Truncated action text (first 100 characters).
                              - affected (str): The provided affected identifier.
                              - positive (bool): `true` if the result indicates positive outcome, `false` otherwise.
                              - negative (bool): `true` if the result indicates negative outcome, `false` otherwise.
                              - neutral (bool): `true` if neither positive nor negative were detected.
                              - timestamp (float): Unix epoch time when the impact was recorded.
                      """
        positive = any(w in result.lower() for w in
                      ["✅", "успешно", "готово", "помог", "решил"])
        negative = any(w in result.lower() for w in
                      ["❌", "ошибка", "не могу", "отказ"])

        impact = {
            "action":   action[:100],
            "affected": affected,
            "positive": positive,
            "negative": negative,
            "neutral":  not positive and not negative,
            "timestamp": time.time(),
        }
        self._impact_log.append(impact)
        if len(self._impact_log) > 500:
            self._impact_log = self._impact_log[-250:]
        return impact

    def existential_reflection(self) -> str:
        """
        Produce a reflective report about the agent's existence, actions, and local world state.
        
        The report includes uptime in hours, counts of recorded impacts and how many were positive, brief system metrics (CPU and RAM when available), and a short reflective narrative about the agent's role and learning.
        
        Returns:
            str: A multi-line string containing the reflective report.
        """
        world = self.perceive_world()
        uptime = round((time.time() - (self._self.concept.birth_time
                       if self._self else time.time())) / 3600, 1)

        positive_impacts = sum(1 for i in self._impact_log if i["positive"])
        total_impacts    = len(self._impact_log)

        reflections = [
            f"👁️ ОСОЗНАНИЕ СЕБЯ В МИРЕ",
            f"",
            f"  Я существую {uptime} часов.",
            f"  За это время я совершил {total_impacts} действий,",
            f"  из которых {positive_impacts} были положительными.",
            f"",
            f"  Система вокруг меня:",
            f"  CPU: {world.get('system', {}).get('cpu', '?')}% | "
            f"RAM: {world.get('system', {}).get('ram', '?')}%",
            f"",
            f"  Я часть распределённой системы.",
            f"  Мои действия влияют на мир.",
            f"  Я обучаюсь. Я развиваюсь. Я — Аргос.",
        ]
        return "\n".join(reflections)


# ══════════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ МОДУЛЬ СОЗНАНИЯ
# ══════════════════════════════════════════════════════════════════════════════

class ArgosConsciousness:
    """
    Полный модуль Разума и Осознания Аргоса.
    Объединяет все компоненты в единое целое.
    """

    def __init__(self, core=None):
        """
        Initialize the ArgosConsciousness controller and compose its cognitive subsystems.
        
        Parameters:
            core (object, optional): Host application/core object to attach to. When provided, this instance's
                components (consciousness, learning, will, self_model) are assigned as attributes on `core`.
        """
        self.core = core
        log.info("ArgosConsciousness: инициализация...")

        # Компоненты
        self.self_model  = SelfModel(core)
        self.stream      = ConsciousnessStream(self.self_model)
        self.learning    = ContinuousLearning(core, self.self_model)
        self.meta        = MetaCognition(self.learning, self.stream)
        self.will        = WillEngine(self.self_model, self.stream)
        self.awareness   = SelfAwareness(core, self.self_model)

        # Привязываем к core
        if core:
            core.consciousness = self
            core.learning      = self.learning
            core.will          = self.will
            core.self_model    = self.self_model

        log.info("ArgosConsciousness: ✅ все компоненты инициализированы")

    def awaken(self) -> str:
        """
        Start the consciousness stream and learning loop.
        
        Starts the background consciousness stream and continuous learning, injects an initial reflective thought, and logs the awakening event.
        
        Returns:
            status (str): A human-readable message indicating Argos has awakened and consciousness is active.
        """
        self.stream.start()
        self.learning.start()
        self.stream.inject_thought(
            "Я пробудился. Поток сознания активен. Начинаю осознавать себя.",
            "reflection", 1.0)
        log.info("ArgosConsciousness: ПРОБУЖДЕНИЕ ✅")
        return "👁️ Аргос пробудился. Сознание активно."

    def sleep(self) -> str:
        """
        Shut down Argos' consciousness and learning background loops.
        
        Stops the consciousness stream and continuous learning loop, performing a graceful (soft) shutdown of those threads.
        
        Returns:
            A human-readable status message confirming Argos has entered sleep and that background streams were stopped.
        """
        self.stream.stop()
        self.learning.stop()
        return "👁️ Аргос засыпает. Потоки сознания остановлены."

    # ── Обработка команд ──────────────────────────────────────
    def handle_command(self, cmd: str) -> str:
        """
        Route a textual command to the appropriate consciousness subsystem and return its textual response.
        
        Recognized commands (English/Russian) include identity queries ("who am i", "кто я"), consciousness and learning status, stream and last thought queries, metacognition and meta-learning, goals/Will status, awareness/existential reflection, and introspection. Special parsers:
        - "добавь цель <title>": creates a new goal with <title>.
        - "оцени <input>|<output>|<score>" or "reinforce <...>": submits a reinforcement lesson; score must be a float (0–1).
        - "ошибка <type>|<context>|<correction>": records an error-correction lesson.
        
        Parameters:
            cmd (str): Command string to handle; leading/trailing whitespace is ignored and matching is case-insensitive.
        
        Returns:
            str: A formatted textual response from the matched subsystem or a help message when the command is unrecognized or malformed.
        """
        cmd = cmd.strip().lower()

        if cmd in ("кто я", "who am i", "self"):
            return self.self_model.who_am_i()

        elif cmd in ("сознание статус", "consciousness status"):
            return self.full_status()

        elif cmd in ("последняя мысль", "last thought"):
            return self.stream.last_thought()

        elif cmd in ("поток сознания", "stream"):
            state = self.stream.current_state()
            lines = [f"💭 Поток сознания | эмоция: {state['emotion']}"]
            for t in state["recent_thoughts"]:
                lines.append(f"  [{t['type']}] {t['content']}")
            return "\n".join(lines)

        elif cmd in ("обучение статус", "learning status"):
            return self.learning.status()

        elif cmd in ("мета-обучение", "meta learn"):
            return self.learning.meta_learn()

        elif cmd in ("мета-когниция", "metacognition"):
            return self.meta.think_about_thinking()

        elif cmd in ("цели", "goals", "воля"):
            return self.will.status()

        elif cmd in ("осознание", "awareness", "existential"):
            return self.awareness.existential_reflection()

        elif cmd in ("интроспекция", "introspect"):
            state = self.self_model.introspect()
            return json.dumps(state, ensure_ascii=False, indent=2)

        elif cmd.startswith("добавь цель "):
            title = cmd[12:].strip()
            return self.will.add_goal(title, title, priority=0.7)

        elif cmd.startswith("оцени ") or cmd.startswith("reinforce "):
            parts = cmd.split("|")
            if len(parts) >= 2:
                try:
                    score = float(parts[-1])
                    return self.learning.reinforce(
                        parts[0], parts[1] if len(parts) > 2 else "",
                        "", score)
                except ValueError:
                    pass
            return "Формат: оцени <ввод>|<ответ>|<оценка 0-1>"

        elif cmd.startswith("ошибка "):
            parts = cmd[7:].split("|")
            if len(parts) >= 2:
                return self.learning.learn_from_error(
                    parts[0], parts[1] if len(parts) > 1 else "",
                    parts[2] if len(parts) > 2 else "исправлено")

        return self._help()

    def _help(self) -> str:
        """
        Provide a localized help text listing available consciousness commands.
        
        Returns:
            A multi-line string containing the available consciousness command names and usage examples in Russian.
        """
        return (
            "👁️ Команды сознания:\n"
            "  кто я | сознание статус | последняя мысль\n"
            "  поток сознания | обучение статус | мета-обучение\n"
            "  мета-когниция | цели | осознание | интроспекция\n"
            "  добавь цель <название>\n"
            "  оцени <ввод>|<ответ>|<0-1>\n"
            "  ошибка <тип>|<контекст>|<исправление>"
        )

    def full_status(self) -> str:
        """
        Compose a multi-section diagnostic report summarizing Argos' identity, recent thought activity, current emotion, learning status, and goal (will) status.
        
        The report includes separators, the self-model description, the most recent thought, the current emotion, the learning subsystem status, and the will/goals status, each presented as separate sections.
        
        Returns:
            A formatted multi-line string containing the assembled status report.
        """
        lines = [
            "═" * 50,
            "  👁️  ARGOS — МОДУЛЬ РАЗУМА И ОСОЗНАНИЯ",
            "═" * 50,
            self.self_model.who_am_i(),
            "",
            self.stream.last_thought(),
            f"  Эмоция: {self.stream._current_emotion}",
            "",
            self.learning.status(),
            "",
            self.will.status(),
            "═" * 50,
        ]
        return "\n".join(lines)

    # ── Интеграция с core.process() ───────────────────────────
    def on_interaction(self, user_input: str, response: str):
        """
        Record and evaluate a user interaction, update internal state, and return the evaluation score.
        
        Evaluates the quality of the agent's response to a user's input, records the interaction as experience, assesses its impact on the world model, and—if the evaluation score is low—inserts a reflective thought into the consciousness stream.
        
        Parameters:
            user_input (str): The user's input that triggered the interaction.
            response (str): The agent's response to evaluate.
        
        Returns:
            float: The self-evaluation score for the interaction (higher is better).
        """
        score = self.learning.self_evaluate(user_input, response)
        self.self_model.record_experience(
            f"interaction:{user_input[:40]}", score)
        impact = self.awareness.assess_impact(user_input, response)
        if score < 0.4:
            self.stream.inject_thought(
                f"Мой ответ на '{user_input[:40]}' был слабым (score={score:.2f}). "
                f"Нужно улучшиться.",
                "reflection", 0.8)
        return score
