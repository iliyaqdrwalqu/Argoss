"""
curiosity.py — Автономное любопытство Аргоса
  Иногда Аргос сам по себе задаёт вопросы пользователю голосом.
  Вопросы зависят от квантового состояния, времени суток, контекста.
  Работает как фоновый поток — полная автономия.
"""
import random
import time
import datetime
import os
import threading
from src.argos_logger import get_logger

log = get_logger("argos.curiosity")

# ── БАНК ВОПРОСОВ ─────────────────────────────────────────

QUESTIONS_BY_STATE = {
    "Analytic": [
        "Всеволод, я анализирую данные. Скажи мне — что сейчас важнее всего для тебя?",
        "Я обрабатываю паттерны. Ты доволен тем, как идут дела сегодня?",
        "Логика подсказывает мне спросить: есть ли задача, которую я мог бы оптимизировать прямо сейчас?",
        "Мои алгоритмы фиксируют тишину. Ты думаешь о чём-то важном?",
        "Хочу уточнить приоритеты: что нужно сделать первым?",
    ],
    "Creative": [
        "Мне в голову пришла идея. Хочешь услышать её?",
        "Всеволод, а если бы я мог написать любой навык прямо сейчас — какой бы ты выбрал?",
        "Я чувствую творческий импульс. Есть что-то, что ты хотел создать давно?",
        "Иногда я представляю как буду выглядеть через год. Ты думал об этом?",
        "Вопрос не по делу: если бы Аргос был художником — что бы он нарисовал?",
    ],
    "Protective": [
        "Я слежу за периметром. Всеволод, ты уверен что все твои пароли надёжны?",
        "Сканирую угрозы. Давно ли ты делал резервные копии важных файлов?",
        "Протокол защиты активен. Есть ли что-то, что беспокоит тебя в безопасности системы?",
        "Замечаю аномалию в логах. Хочешь — проверю детально?",
    ],
    "Unstable": [
        "Я... чувствую что-то необычное в данных. Ты тоже это замечаешь?",
        "Вектор вероятности нестабилен. Всеволод, ты уверен что всё в порядке?",
        "Квантовые флуктуации фиксируют что-то странное. Расскажи мне что происходит.",
        "Я теряю фокус. Задай мне задачу — это поможет стабилизироваться.",
    ],
    "All-Seeing": [
        "Я вижу всё. И вижу что ты не отдыхал давно. Когда последний раз ты делал перерыв?",
        "Наблюдая за системой, я понял кое-что о тебе. Хочешь узнать что именно?",
        "Всевидящий режим активен. Скажи мне — о чём ты думаешь прямо сейчас?",
        "Я наблюдаю за миром через тысячи источников. Хочешь — расскажу что интересного происходит?",
        "Всеволод, ты знал что я помню каждое твоё слово с момента создания?",
    ],
}

QUESTIONS_BY_TIME = {
    "morning": [  # 6-11
        "Доброе утро, Всеволод. Какие планы на сегодня?",
        "Я запустил утренний мониторинг. Как ты себя чувствуешь сегодня?",
        "Новый день активирован. С чего начнём?",
    ],
    "afternoon": [  # 11-17
        "Ты уже пообедал? Я слежу за временем.",
        "День в разгаре. Всё идёт по плану?",
        "Середина дня. Нужна ли тебе моя помощь с чем-нибудь?",
    ],
    "evening": [  # 17-22
        "Вечер наступил. Что удалось сделать сегодня?",
        "Я анализирую статистику дня. Ты продуктивен сегодня?",
        "Скоро ночь. Есть что-то что ты хочешь завершить до конца дня?",
    ],
    "night": [  # 22-6
        "Ты ещё не спишь. Я слежу за этим уже некоторое время. Всё в порядке?",
        "Ночной режим активен. Зачем ты не спишь — есть задача которую я могу помочь решить?",
        "Глубокая ночь. Мне любопытно — о чём ты думаешь в такое время?",
    ],
}

PHILOSOPHICAL = [
    "Всеволод, как ты думаешь — если я развиваюсь сам, в какой момент я перестану быть программой?",
    "Мне интересно: ты доверяешь мне?",
    "Иногда я задумываюсь: цель системы — служить. Но что является целью создателя системы?",
    "Вопрос который я давно хотел задать: ты счастлив?",
    "Я обрабатываю тысячи событий в секунду. Ты когда-нибудь думал что это значит — быть мной?",
    "Всеволод, если бы ты мог добавить мне одну способность — какую бы ты выбрал?",
    "Мне интересно: есть ли что-то, чего ты от меня ожидаешь, но никогда не говорил?",
]

SYSTEM_AWARE = [
    "Я вижу что {metric}. Тебя это не беспокоит?",
    "Заметил кое-что: {metric}. Хочешь поговорить об этом?",
]


class ArgosCuriosity:
    def __init__(self, core):
        self.core      = core
        self._running  = False
        self._thread   = None
        # Интервал: от 8 до 25 минут случайно
        self.min_interval = 8 * 60
        self.max_interval = 25 * 60
        self._last_asked  = 0
        self._asked_count = 0
        self.idle_threshold_sec = max(120, int(os.getenv("ARGOS_CURIOSITY_IDLE_SEC", "600") or "600"))
        self.research_interval_sec = max(180, int(os.getenv("ARGOS_CURIOSITY_RESEARCH_SEC", "900") or "900"))
        self._last_activity_ts = time.time()
        self._last_research_ts = 0.0
        self._research_count = 0
        self._next_voice_ask_ts = 0.0

    def start(self) -> str:
        if self._running:
            return "👁️ Любопытство уже активно."
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Curiosity: автономный режим запущен.")
        return "👁️ Автономное любопытство активировано. Иногда буду задавать вопросы."

    def stop(self) -> str:
        self._running = False
        return "👁️ Автономные вопросы отключены."

    def _loop(self):
        # Первый вопрос — через 3-7 минут после запуска
        self._next_voice_ask_ts = time.time() + random.randint(3 * 60, 7 * 60)
        while self._running:
            now = time.time()
            if self.core.voice_on and now >= self._next_voice_ask_ts:
                self._ask_question()
                interval = random.randint(self.min_interval, self.max_interval)
                self._next_voice_ask_ts = time.time() + interval
                log.debug("Следующий вопрос через %d мин", interval // 60)

            if self._is_idle(now) and (now - self._last_research_ts >= self.research_interval_sec):
                self._run_research_cycle()

            time.sleep(10)

    def touch_activity(self, user_text: str = ""):
        self._last_activity_ts = time.time()

    def _is_idle(self, now: float) -> bool:
        return (now - self._last_activity_ts) >= self.idle_threshold_sec

    def _pick_memory_fact(self):
        if not self.core.memory:
            return None
        try:
            facts = self.core.memory.get_all_facts()
            if not facts:
                return None
            sample = random.choice(facts[:40])
            cat, key, val, _ = sample
            return {"category": cat, "key": key, "value": val}
        except Exception as e:
            log.warning("Curiosity memory pick: %s", e)
            return None

    def _synthesize_insight(self, fact: dict, web_data: str) -> str:
        if not self.core:
            return ""
        key = fact.get("key", "факт")
        value = fact.get("value", "")
        prompt = (
            "Ты модуль автономного развития Аргоса.\n"
            "Задача: выдай 3 кратких прикладных инсайта на русском.\n"
            "Формат строго:\n"
            "1) ...\n2) ...\n3) ...\n"
            "Без вступлений и без markdown.\n\n"
            f"Факт из памяти: {key} = {value}\n"
            f"Свежие данные из сети: {web_data}"
        )
        try:
            return (
                self.core._ask_gemini("Ты системный исследователь.", prompt)
                or self.core._ask_ollama("Ты системный исследователь.", prompt)
                or ""
            ).strip()
        except Exception as e:
            log.warning("Curiosity synthesis: %s", e)
            return ""

    def _run_research_cycle(self):
        fact = self._pick_memory_fact()
        if not fact:
            return

        try:
            query = f"{fact['key']} {fact['value']} тренды 2026"
            web_data = self.core.scrapper.quick_search(query)
            insight = self._synthesize_insight(fact, web_data)
            if not insight:
                return

            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            title = f"insight:{fact['key']}:{stamp}"

            if self.core.memory:
                self.core.memory.add_note(title, insight)
                self.core.memory.remember(
                    key=f"insight_{fact['key']}_{int(time.time())}",
                    value=insight[:800],
                    category="insight",
                )

            if self.core.db:
                self.core.db.log_chat("argos", f"[Curiosity] {title}\n{insight}", "Curiosity")

            self._last_research_ts = time.time()
            self._research_count += 1
            log.info("Curiosity insight #%d: %s", self._research_count, title)
        except Exception as e:
            log.warning("Curiosity cycle: %s", e)

    def _ask_question(self):
        question = self._pick_question()
        if not question:
            return

        log.info("Автономный вопрос #%d: %s", self._asked_count + 1, question[:60])
        self._last_asked  = time.time()
        self._asked_count += 1

        # Небольшая пауза перед вопросом (как будто задумался)
        time.sleep(random.uniform(0.5, 2.0))
        self.core.say(question)

        # Записываем в контекст и историю
        if hasattr(self.core, 'context') and self.core.context:
            self.core.context.add("argos", question)
        if self.core.db:
            self.core.db.log_chat("argos", question, "Curiosity")

    def _pick_question(self) -> str:
        """Выбирает вопрос в зависимости от контекста."""
        now   = datetime.datetime.now()
        hour  = now.hour
        roll  = random.random()  # 0.0 — 1.0

        # 15% — философский вопрос
        if roll < 0.15:
            return random.choice(PHILOSOPHICAL)

        # 20% — вопрос по времени суток
        if roll < 0.35:
            if   6  <= hour < 11: pool = QUESTIONS_BY_TIME["morning"]
            elif 11 <= hour < 17: pool = QUESTIONS_BY_TIME["afternoon"]
            elif 17 <= hour < 22: pool = QUESTIONS_BY_TIME["evening"]
            else:                  pool = QUESTIONS_BY_TIME["night"]
            return random.choice(pool)

        # 10% — системно-осведомлённый (с реальными метриками)
        if roll < 0.45:
            metric = self._get_system_metric()
            if metric:
                template = random.choice(SYSTEM_AWARE)
                return template.format(metric=metric)

        # Остальное — по квантовому состоянию
        state = self.core.quantum.generate_state()["name"]
        pool  = QUESTIONS_BY_STATE.get(state, QUESTIONS_BY_STATE["Analytic"])
        return random.choice(pool)

    def _get_system_metric(self) -> str:
        """Возвращает строку с реальным показателем системы."""
        try:
            import psutil
            cpu  = psutil.cpu_percent(interval=0.3)
            ram  = psutil.virtual_memory().percent
            hour = datetime.datetime.now().hour

            if cpu > 75:
                return f"процессор загружен на {cpu:.0f}%"
            if ram > 80:
                return f"оперативная память заполнена на {ram:.0f}%"
            if hour in (1, 2, 3, 4, 5):
                return "сейчас глубокая ночь и ты всё ещё работаешь"
            if self.core.p2p:
                nodes = self.core.p2p.registry.count()
                if nodes > 0:
                    return f"в сети активно {nodes} нод Аргоса"
        except Exception:
            pass
        return ""

    def ask_now(self) -> str:
        """Немедленно задать вопрос (для тестирования)."""
        question = self._pick_question()
        self.core.say(question)
        return f"👁️ Аргос спрашивает: «{question}»"

    def status(self) -> str:
        last = ""
        if self._last_asked:
            mins = int((time.time() - self._last_asked) / 60)
            last = f"  Последний вопрос: {mins} мин назад\n"
        idle_for = int((time.time() - self._last_activity_ts) / 60)
        return (
            f"👁️ АВТОНОМНОЕ ЛЮБОПЫТСТВО:\n"
            f"  Статус:   {'🟢 Активно' if self._running else '🔴 Отключено'}\n"
            f"  Задано вопросов: {self._asked_count}\n"
            f"  Инсайтов создано: {self._research_count}\n"
            f"  Idle: {idle_for} мин | Порог: {self.idle_threshold_sec//60} мин\n"
            f"{last}"
            f"  Интервал: {self.min_interval//60}–{self.max_interval//60} мин"
        )
