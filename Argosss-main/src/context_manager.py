"""
context_manager.py v2.0 — Трёхуровневый контекст диалога
  Уровень 1: Локальный (текущая сессия, скользящее окно)
  Уровень 2: Долгосрочная память (SQLite факты)
  Уровень 3: Семантический поиск (TF-IDF / embeddings)
  
  Квантовые профили: каждое состояние имеет свои параметры контекста.
"""
import re, time, math
from collections import deque
from src.argos_logger import get_logger

log = get_logger("argos.context")


# ── КВАНТОВЫЕ ПРОФИЛИ КОНТЕКСТА ───────────────────────────
QUANTUM_PROFILES = {
    "Analytic": {
        "window":     6,      # узкое окно — меньше шума
        "memory_use": False,  # без долгосрочных воспоминаний
        "creativity": 0.2,   # низкая температура ИИ
        "description": "Чистый ввод/вывод, минимальный шум",
        "system_hint": "Отвечай чётко, структурированно. Только факты.",
        "allow_root_cmds": True,
    },
    "Creative": {
        "window":     15,
        "memory_use": True,
        "creativity": 0.9,
        "description": "Расширенный контекст, цепочки разрешены",
        "system_hint": "Будь творческим, предлагай неожиданные решения.",
        "allow_root_cmds": False,
    },
    "Protective": {
        "window":     8,
        "memory_use": False,
        "creativity": 0.1,
        "description": "Фокус на безопасности, root-команды ограничены",
        "system_hint": "Приоритет — безопасность. Предупреждай о рисках.",
        "allow_root_cmds": False,  # заблокировано в защитном режиме
    },
    "Unstable": {
        "window":     4,
        "memory_use": False,
        "creativity": 0.5,
        "description": "Нестабильное состояние — минимальный контекст",
        "system_hint": "Запрашивай уточнения, не делай предположений.",
        "allow_root_cmds": False,
    },
    "All-Seeing": {
        "window":     20,
        "memory_use": True,
        "creativity": 0.7,
        "description": "Полный доступ к памяти, максимальный контекст",
        "system_hint": "Используй всю доступную информацию для ответа.",
        "allow_root_cmds": True,
    },
    "System": {
        "window":     5,
        "memory_use": False,
        "creativity": 0.0,
        "description": "Системные команды — без диалога",
        "system_hint": "Выполняй команды, отвечай кратко.",
        "allow_root_cmds": True,
    },
}


# ── УРОВЕНЬ 3: СЕМАНТИЧЕСКИЙ ПОИСК ───────────────────────
class SemanticLayer:
    """TF-IDF семантический поиск по истории.
    Не требует тяжёлых зависимостей — работает на чистом Python."""

    def __init__(self, max_docs: int = 200):
        self._docs: list[dict] = []   # {"text": str, "role": str, "ts": float}
        self._max  = max_docs

    def add(self, text: str, role: str = "user"):
        self._docs.append({"text": text, "role": role, "ts": time.time()})
        if len(self._docs) > self._max:
            self._docs = self._docs[-self._max:]

    def _tokenize(self, text: str) -> list:
        return re.findall(r'\b\w+\b', text.lower())

    def _tfidf_score(self, query_tokens: list, doc_text: str) -> float:
        doc_tokens = self._tokenize(doc_text)
        if not doc_tokens:
            return 0.0
        tf = {}
        for t in doc_tokens:
            tf[t] = tf.get(t, 0) + 1
        n_docs = len(self._docs) + 1
        score  = 0.0
        for t in set(query_tokens):
            tf_val  = tf.get(t, 0) / len(doc_tokens)
            df      = sum(1 for d in self._docs if t in self._tokenize(d["text"]))
            idf     = math.log((n_docs + 1) / (df + 1)) + 1
            score  += tf_val * idf
        return score

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if not self._docs or not query:
            return []
        q_tokens = self._tokenize(query)
        scored   = [(self._tfidf_score(q_tokens, d["text"]), d) for d in self._docs]
        scored.sort(key=lambda x: -x[0])
        return [d for score, d in scored[:top_k] if score > 0.1]

    def recall_context(self, query: str, top_k: int = 3) -> str:
        results = self.search(query, top_k)
        if not results:
            return ""
        lines = ["Похожие прошлые фрагменты разговора:"]
        for d in results:
            icon = "👤" if d["role"] == "user" else "👁️"
            ago  = _ago(d["ts"])
            lines.append(f"  {icon} ({ago}): {d['text'][:100]}")
        return "\n".join(lines)


def _ago(ts: float) -> str:
    s = int(time.time() - ts)
    if s < 60: return f"{s}с назад"
    if s < 3600: return f"{s//60}м назад"
    return f"{s//3600}ч назад"


# ── ОСНОВНОЙ КЛАСС ────────────────────────────────────────
class DialogContext:
    def __init__(self, max_turns: int = 10, quantum_state: str = "Analytic"):
        self._quantum_state = quantum_state
        self._profile       = QUANTUM_PROFILES.get(quantum_state, QUANTUM_PROFILES["Analytic"])
        self._window        = self._profile["window"]
        # Уровень 1: локальный буфер
        self._local  = deque(maxlen=self._window * 2)
        # Уровень 3: семантика
        self._semantic = SemanticLayer()
        # Разделённые контексты
        self._chat_buf    = deque(maxlen=20)   # диалог
        self._command_buf = deque(maxlen=10)   # команды
        # Внешняя память (уровень 2 — ссылка на ArgosMemory)
        self.memory_ref = None

    # ── КВАНТОВЫЙ ПРОФИЛЬ ────────────────────────────────
    def set_quantum_state(self, state: str):
        profile = QUANTUM_PROFILES.get(state)
        if not profile:
            return
        old_state     = self._quantum_state
        self._quantum_state = state
        self._profile = profile
        new_window    = profile["window"]
        if new_window != self._window:
            self._window = new_window
            self._local  = deque(list(self._local)[-new_window*2:], maxlen=new_window*2)
        log.debug("Квантовый профиль: %s → %s (окно=%d)", old_state, state, new_window)

    @property
    def allow_root(self) -> bool:
        return self._profile.get("allow_root_cmds", True)

    @property
    def system_hint(self) -> str:
        return self._profile.get("system_hint", "")

    @property
    def creativity(self) -> float:
        return self._profile.get("creativity", 0.5)

    # ── ДОБАВЛЕНИЕ СООБЩЕНИЙ ─────────────────────────────
    def add(self, role: str, text: str, is_command: bool = False):
        msg = {"role": role, "text": text, "ts": time.time(), "cmd": is_command}
        self._local.append(msg)
        self._semantic.add(text, role)
        if is_command:
            self._command_buf.append(msg)
        else:
            self._chat_buf.append(msg)

    def add_command(self, role: str, text: str):
        self.add(role, text, is_command=True)

    # ── ФОРМИРОВАНИЕ КОНТЕКСТА ───────────────────────────
    def get_prompt_context(self, query: str = "") -> str:
        parts = []

        # 1. Системная подсказка по квантовому состоянию
        if self.system_hint:
            parts.append(f"[{self._quantum_state}] {self.system_hint}")

        # 2. Долгосрочная память (уровень 2)
        if self._profile.get("memory_use") and self.memory_ref:
            mc = self.memory_ref.get_context()
            if mc:
                parts.append(mc)

        # 3. Семантический recall (уровень 3)
        if query:
            sr = self._semantic.recall_context(query, top_k=2)
            if sr:
                parts.append(sr)

        # 4. Локальный контекст (уровень 1) — только диалог, без команд
        local_msgs = [m for m in self._local if not m["cmd"]]
        if local_msgs:
            lines = ["Текущий диалог:"]
            for m in local_msgs[-self._window:]:
                icon = "👤" if m["role"] == "user" else "👁️"
                lines.append(f"  {icon}: {m['text'][:150]}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts) if parts else ""

    def get_gemini_messages(self) -> list:
        """Для Gemini multi-turn API."""
        msgs = []
        for m in self._local:
            role = "user" if m["role"] == "user" else "model"
            msgs.append({"role": role, "parts": [{"text": m["text"]}]})
        return msgs

    # ── КОМАНДЫ ──────────────────────────────────────────
    def clear(self) -> str:
        self._local.clear()
        self._chat_buf.clear()
        self._command_buf.clear()
        return "🧹 Контекст диалога очищен."

    def summary(self) -> str:
        prof = self._profile
        return (f"💬 КОНТЕКСТ ДИАЛОГА:\n"
                f"  Состояние:     {self._quantum_state} — {prof['description']}\n"
                f"  Окно:          {len(self._local)}/{self._window*2} сообщений\n"
                f"  Команд:        {len(self._command_buf)}\n"
                f"  Семант. индекс:{len(self._semantic._docs)} фрагментов\n"
                f"  Допуск root:   {'✅' if self.allow_root else '🚫'}\n"
                f"  Память:        {'✅' if prof['memory_use'] else '—'}\n"
                f"  Креативность:  {int(self.creativity*100)}%")

    def get_command_history(self, n: int = 5) -> str:
        cmds = list(self._command_buf)[-n:]
        if not cmds:
            return "История команд пуста."
        lines = [f"⌨️ ПОСЛЕДНИЕ {len(cmds)} КОМАНД:"]
        for m in cmds:
            ago = _ago(m["ts"])
            lines.append(f"  [{ago}] {m['text'][:60]}")
        return "\n".join(lines)

# Backward-compatibility alias
ArgosContextManager = DialogContext
