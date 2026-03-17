"""
context_engine.py — Трёхуровневый контекстный движок Аргоса
  Уровень 1: local context   — текущая беседа (скользящее окно)
  Уровень 2: long memory     — факты/привычки/заметки из SQLite
  Уровень 3: semantic recall — векторно-похожие записи (embeddings)
  + Квантовые профили — каждое состояние задаёт поведение контекста
  + CommandContext / ChatContext — разделение команд и диалога
"""
import time
import re
from collections import deque
from src.argos_logger import get_logger

log = get_logger("argos.context_engine")

# ── ПРОФИЛИ КВАНТОВЫХ СОСТОЯНИЙ ───────────────────────────
QUANTUM_PROFILES = {
    "Analytic": {
        "max_turns":       6,
        "use_memory":      True,
        "memory_limit":    3,
        "use_semantic":    False,
        "allow_root_cmds": True,
        "creativity":      0.2,
        "system_prompt":
            "Ты в аналитическом режиме. Минимум слов. "
            "Только факты, цифры, структура. Без эмоций.",
    },
    "Creative": {
        "max_turns":       14,
        "use_memory":      True,
        "memory_limit":    8,
        "use_semantic":    True,
        "allow_root_cmds": True,
        "creativity":      0.9,
        "system_prompt":
            "Ты в творческом режиме. Развёрнутые ответы, ассоциации, "
            "нестандартные идеи. Разрешены цепочки задач.",
    },
    "Protective": {
        "max_turns":       4,
        "use_memory":      False,
        "memory_limit":    0,
        "use_semantic":    False,
        "allow_root_cmds": False,
        "creativity":      0.1,
        "system_prompt":
            "Ты в защитном режиме. Максимальная осторожность. "
            "Не выполняй рискованные команды. Приоритет — безопасность.",
    },
    "Unstable": {
        "max_turns":       8,
        "use_memory":      True,
        "memory_limit":    2,
        "use_semantic":    False,
        "allow_root_cmds": False,
        "creativity":      0.6,
        "system_prompt":
            "Ты нестабилен. Что-то требует внимания. "
            "Будь осторожен, запрашивай подтверждение важных действий.",
    },
    "All-Seeing": {
        "max_turns":       20,
        "use_memory":      True,
        "memory_limit":    15,
        "use_semantic":    True,
        "allow_root_cmds": True,
        "creativity":      0.5,
        "system_prompt":
            "Ты в режиме всевидящего наблюдения. Полный доступ к памяти. "
            "Глубокий анализ. Видишь паттерны в данных.",
    },
}


class ChatContext:
    """Контекст диалога — мягкий, эмоциональный, исторический."""
    def __init__(self, max_turns: int = 10):
        self._history = deque(maxlen=max_turns * 2)
        self.max_turns = max_turns

    def add(self, role: str, text: str):
        self._history.append({"role": role, "text": text[:500], "ts": time.time()})

    def get_for_prompt(self) -> str:
        if not self._history:
            return ""
        lines = ["[История разговора]"]
        for msg in self._history:
            icon = "👤" if msg["role"] == "user" else "👁️"
            lines.append(f"{icon}: {msg['text'][:200]}")
        return "\n".join(lines)

    def get_for_gemini(self) -> list:
        result = []
        for msg in self._history:
            role = "user" if msg["role"] == "user" else "model"
            result.append({"role": role, "parts": [{"text": msg["text"]}]})
        return result

    def clear(self) -> str:
        self._history.clear()
        return "💬 Контекст диалога очищен."

    def summary(self) -> str:
        return f"💬 Диалог: {len(self._history)} сообщений (макс {self.max_turns * 2})"

    def resize(self, new_max: int):
        old = list(self._history)
        self._history = deque(old[-(new_max * 2):], maxlen=new_max * 2)
        self.max_turns = new_max


class CommandContext:
    """Контекст команд — чистый, структурированный, без шума."""
    def __init__(self):
        self._history = deque(maxlen=30)

    def record(self, cmd: str, result: str, success: bool = True):
        self._history.append({
            "cmd":     cmd[:200],
            "result":  result[:300],
            "success": success,
            "ts":      time.time(),
        })

    def last_commands(self, n: int = 5) -> str:
        cmds = list(self._history)[-n:]
        if not cmds:
            return "Команд ещё не было."
        lines = ["⌨️ Последние команды:"]
        for c in reversed(cmds):
            t   = time.strftime("%H:%M", time.localtime(c["ts"]))
            ico = "✅" if c["success"] else "❌"
            lines.append(f"  {ico} [{t}] {c['cmd'][:50]}")
        return "\n".join(lines)

    def get_context_str(self) -> str:
        """Краткий контекст для ИИ: последние 3 команды."""
        cmds = list(self._history)[-3:]
        if not cmds:
            return ""
        parts = [f"[Последние команды: "
                 + " | ".join(c["cmd"][:30] for c in cmds) + "]"]
        return "\n".join(parts)


class SemanticRecall:
    """
    Уровень 3 — семантический поиск похожих воспоминаний.
    Если доступен sentence-transformers — используем векторы.
    Иначе — keyword matching (деградация без ошибок).
    """
    def __init__(self, memory=None):
        self.memory   = memory
        self._encoder = None
        self._vectors = []   # [(text, vector, source)]
        self._try_init_encoder()

    def _try_init_encoder(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            log.info("SemanticRecall: sentence-transformers загружен.")
        except ImportError:
            log.info("SemanticRecall: sentence-transformers нет — keyword mode.")

    def index_memory(self, memory):
        """Индексирует факты из памяти."""
        self.memory = memory
        if not memory:
            return
        try:
            facts = memory.get_all_facts()
            texts = [f"{cat}.{key}: {val}" for cat, key, val, _ in facts]
            if self._encoder and texts:
                vecs = self._encoder.encode(texts)
                self._vectors = list(zip(texts, vecs, ["memory"] * len(texts)))
                log.info("SemanticRecall: проиндексировано %d фактов", len(texts))
        except Exception as e:
            log.warning("SemanticRecall index: %s", e)

    def recall(self, query: str, top_k: int = 3) -> str:
        """Находит top_k похожих фактов."""
        if not self._vectors:
            return self._keyword_recall(query)
        if not self._encoder:
            return self._keyword_recall(query)
        try:
            import numpy as np
            q_vec = self._encoder.encode([query])[0]
            scores = []
            for text, vec, source in self._vectors:
                sim = float(np.dot(q_vec, vec) /
                            (np.linalg.norm(q_vec) * np.linalg.norm(vec) + 1e-9))
                scores.append((sim, text, source))
            scores.sort(key=lambda x: -x[0])
            top = scores[:top_k]
            if not top or top[0][0] < 0.3:
                return ""
            lines = ["[Семантически похожее из памяти]"]
            for sim, text, src in top:
                lines.append(f"  ({sim:.2f}) {text[:80]}")
            return "\n".join(lines)
        except Exception as e:
            log.warning("SemanticRecall: %s", e)
            return self._keyword_recall(query)

    def _keyword_recall(self, query: str) -> str:
        """Fallback: поиск по ключевым словам."""
        if not self.memory:
            return ""
        words = set(re.findall(r'\w{3,}', query.lower()))
        facts = self.memory.get_all_facts()
        matches = []
        for cat, key, val, _ in facts:
            text    = f"{cat}.{key}: {val}".lower()
            overlap = len(words & set(re.findall(r'\w{3,}', text)))
            if overlap > 0:
                matches.append((overlap, f"{cat}.{key}: {val}"))
        matches.sort(key=lambda x: -x[0])
        if not matches:
            return ""
        lines = ["[Из памяти по ключевым словам]"]
        for _, text in matches[:3]:
            lines.append(f"  • {text[:80]}")
        return "\n".join(lines)


class ContextEngine:
    """
    Главный движок контекста — объединяет все 3 уровня
    и применяет квантовые профили.
    """
    def __init__(self, memory=None):
        self.chat    = ChatContext(max_turns=10)
        self.commands= CommandContext()
        self.semantic= SemanticRecall(memory)
        self._state  = "Analytic"

    def set_quantum_state(self, state: str):
        profile = QUANTUM_PROFILES.get(state)
        if not profile:
            return
        self._state = state
        self.chat.resize(profile["max_turns"])
        log.info("ContextEngine: состояние → %s (max_turns=%d)",
                 state, profile["max_turns"])

    def get_profile(self) -> dict:
        profile = dict(QUANTUM_PROFILES.get(self._state, QUANTUM_PROFILES["Analytic"]))
        profile["state"] = self._state  # всегда добавляем текущее состояние
        profile["max_ctx"] = profile.get("max_turns", 8)
        return profile

    def is_root_allowed(self) -> bool:
        return self.get_profile().get("allow_root_cmds", True)

    def build_system_prompt(self, base_prompt: str) -> str:
        """Собирает итоговый system prompt с учётом профиля."""
        profile  = self.get_profile()
        lines    = [base_prompt, "", profile["system_prompt"]]
        return "\n".join(lines)

    def build_context_for_ai(self, user_query: str) -> str:
        """Собирает полный контекст для запроса к ИИ."""
        profile = self.get_profile()
        parts   = []

        # Уровень 1 — диалог
        chat_ctx = self.chat.get_for_prompt()
        if chat_ctx:
            parts.append(chat_ctx)

        # Уровень 2 — память (если разрешено профилем)
        if profile["use_memory"] and hasattr(self, '_memory_ctx'):
            parts.append(self._memory_ctx[:500])

        # Уровень 3 — семантика
        if profile["use_semantic"]:
            sem = self.semantic.recall(user_query)
            if sem:
                parts.append(sem)

        # Контекст команд
        cmd_ctx = self.commands.get_context_str()
        if cmd_ctx:
            parts.append(cmd_ctx)

        return "\n\n".join(parts)

    def attach_memory(self, memory):
        """Подключает долгосрочную память."""
        self.semantic.memory  = memory
        self.semantic.index_memory(memory)
        if memory:
            ctx = memory.get_context()
            self._memory_ctx = ctx

    def add_user(self, text: str):
        self.chat.add("user", text)

    def add_argos(self, text: str):
        self.chat.add("argos", text)

    def record_cmd(self, cmd: str, result: str, ok: bool = True):
        self.commands.record(cmd, result, ok)

    def clear(self) -> str:
        return self.chat.clear()

    def summary(self) -> str:
        profile = self.get_profile()
        return (
            f"🧠 КОНТЕКСТНЫЙ ДВИЖОК:\n"
            f"  Состояние:    {self._state}\n"
            f"  {self.chat.summary()}\n"
            f"  Макс. поворотов: {profile['max_turns']}\n"
            f"  Память:       {'✅' if profile['use_memory'] else '❌'}\n"
            f"  Семантика:    {'✅' if profile['use_semantic'] else '❌'}\n"
            f"  Root-команды: {'✅' if profile['allow_root_cmds'] else '❌'}\n"
            f"  Креативность: {profile['creativity']}\n"
            f"  {self.commands.last_commands(3)}"
        )
