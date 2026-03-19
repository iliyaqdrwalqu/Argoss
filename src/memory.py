"""
memory.py — Долгосрочная память Аргоса
  Запоминает факты о пользователе, предпочтения, заметки.
  Хранится в SQLite + векторный индекс (RAG) + граф знаний.

ПАТЧ [FIX-VECTOR-IMPORT]:
  ArgosVectorStore импортируется лениво (внутри __init__) чтобы
  не падать при отсутствии chromadb/sentence-transformers.
  Если VectorStore недоступен — работаем только на SQLite.
"""
from __future__ import annotations

import os
import sqlite3
import time
import re
import hashlib
from src.argos_logger import get_logger

log = get_logger("argos.memory")
DB_PATH = "data/memory.db"


class ArgosMemory:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.grist = None

        # [FIX-VECTOR-IMPORT] Ленивый импорт — не падаем если chromadb нет
        self.vector = None
        try:
            from src.knowledge.vector_store import ArgosVectorStore
            self.vector = ArgosVectorStore(path="data/chroma")
            log.info("VectorStore: %s", self.vector.mode)
        except Exception as e:
            log.warning("VectorStore недоступен (только SQLite): %s", e)

        self._init_db()
        self._warmup_vector_index()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                category  TEXT NOT NULL DEFAULT 'general',
                key       TEXT NOT NULL,
                value     TEXT NOT NULL,
                ts        TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(category, key)
            );
            CREATE TABLE IF NOT EXISTS notes (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body  TEXT NOT NULL,
                ts    TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                text      TEXT NOT NULL,
                remind_at REAL NOT NULL,
                done      INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                predicate   TEXT NOT NULL,
                object      TEXT NOT NULL,
                object_type TEXT DEFAULT '',
                source      TEXT DEFAULT 'memory',
                ts          TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(subject, predicate, object)
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                text TEXT,
                ts   TEXT DEFAULT (datetime('now','localtime'))
            );
        """)
        self._ensure_fact_columns()
        self.conn.commit()
        log.debug("Memory DB инициализирована.")

    def _ensure_fact_columns(self):
        """Добавляет колонки если БД старой версии."""
        try:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(facts)")}
            if "category" not in cols:
                self.conn.execute("ALTER TABLE facts ADD COLUMN category TEXT DEFAULT 'general'")
                self.conn.commit()
        except Exception:
            pass

    def _warmup_vector_index(self):
        """Индексирует существующие факты в VectorStore при старте."""
        if not self.vector:
            return
        try:
            facts = self.get_all_facts()
            for cat, key, val, _ in facts[:200]:
                self.vector.upsert(
                    text=f"{cat}.{key}: {val}",
                    metadata={"category": cat, "key": key},
                    doc_id=f"fact_{cat}_{key}",
                )
            log.debug("VectorStore: проиндексировано %d фактов", len(facts))
        except Exception as e:
            log.warning("VectorStore warmup: %s", e)

    # ─────────────────────────────────────────────────────────────────────
    # ФАКТЫ
    # ─────────────────────────────────────────────────────────────────────

    def remember(self, key: str, value: str, category: str = "general") -> str:
        """Сохраняет факт в память."""
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO facts (category, key, value) VALUES (?, ?, ?)",
                (category, key, value),
            )
            self.conn.commit()
            # Индексируем в векторной памяти
            if self.vector:
                try:
                    self.vector.upsert(
                        text=f"{category}.{key}: {value}",
                        metadata={"category": category, "key": key},
                        doc_id=f"fact_{category}_{key}",
                    )
                except Exception:
                    pass
            return f"✅ Запомнил: [{category}] {key} = {value}"
        except Exception as e:
            return f"❌ Ошибка сохранения: {e}"

    def parse_and_remember(self, text: str) -> str:
        """Парсит текст вида 'ключ: значение' и запоминает."""
        text = text.strip()
        if ":" in text:
            key, _, val = text.partition(":")
            return self.remember(key.strip(), val.strip())
        return self.remember("заметка", text)

    def get_all_facts(self) -> list[tuple]:
        try:
            rows = self.conn.execute(
                "SELECT category, key, value, ts FROM facts ORDER BY ts DESC LIMIT 500"
            ).fetchall()
            return rows
        except Exception:
            return []

    def get_fact(self, key: str, category: str = "general") -> str | None:
        try:
            row = self.conn.execute(
                "SELECT value FROM facts WHERE category=? AND key=?",
                (category, key),
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def format_memory(self) -> str:
        """Форматирует всю память для показа пользователю."""
        facts = self.get_all_facts()
        if not facts:
            return "🧠 Память пуста."
        lines = ["🧠 ПАМЯТЬ АРГОСА:"]
        current_cat = None
        for cat, key, val, ts in facts[:50]:
            if cat != current_cat:
                lines.append(f"\n  [{cat}]")
                current_cat = cat
            lines.append(f"    {key}: {val}")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # ПОИСК (RAG)
    # ─────────────────────────────────────────────────────────────────────

    def get_rag_context(self, query: str, top_k: int = 5) -> str:
        """Семантический поиск по памяти."""
        if self.vector:
            try:
                results = self.vector.search(query, top_k=top_k)
                if results:
                    lines = ["📚 Из памяти:"]
                    for r in results:
                        lines.append(f"  • {r['text'][:120]}")
                    return "\n".join(lines)
            except Exception as e:
                log.warning("RAG search vector: %s", e)

        # Fallback — keyword поиск по SQLite
        return self._sqlite_search(query, top_k)

    def _sqlite_search(self, query: str, top_k: int = 5) -> str:
        words = re.findall(r"\w{3,}", query.lower())
        if not words:
            return ""
        try:
            rows = self.conn.execute(
                "SELECT category, key, value FROM facts"
            ).fetchall()
            scored = []
            for cat, key, val in rows:
                text = f"{cat} {key} {val}".lower()
                score = sum(1 for w in words if w in text)
                if score > 0:
                    scored.append((score, cat, key, val))
            scored.sort(reverse=True)
            if not scored:
                return ""
            lines = ["📚 Из памяти (ключевой поиск):"]
            for _, cat, key, val in scored[:top_k]:
                lines.append(f"  • [{cat}] {key}: {val[:100]}")
            return "\n".join(lines)
        except Exception:
            return ""

    # ─────────────────────────────────────────────────────────────────────
    # ЗАМЕТКИ
    # ─────────────────────────────────────────────────────────────────────

    def add_note(self, title: str, body: str) -> str:
        try:
            self.conn.execute(
                "INSERT INTO notes (title, body) VALUES (?, ?)", (title, body)
            )
            self.conn.commit()
            return f"✅ Заметка сохранена: {title}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def get_notes(self, limit: int = 10) -> str:
        try:
            rows = self.conn.execute(
                "SELECT id, title, body, ts FROM notes ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
            if not rows:
                return "📝 Заметок нет."
            lines = ["📝 ЗАМЕТКИ:"]
            for row_id, title, body, ts in rows:
                lines.append(f"  [{row_id}] {title}: {body[:80]}  ({ts[:16]})")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def delete_note(self, note_id: int) -> str:
        try:
            self.conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            self.conn.commit()
            return f"✅ Заметка {note_id} удалена."
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def read_note(self, note_id: int) -> str:
        try:
            row = self.conn.execute(
                "SELECT title, body, ts FROM notes WHERE id=?", (note_id,)
            ).fetchone()
            if not row:
                return f"❌ Заметка #{note_id} не найдена."
            title, body, ts = row
            return f"📝 #{note_id} [{ts[:16]}] {title}\n\n{body}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    # ─────────────────────────────────────────────────────────────────────
    # НАПОМИНАНИЯ
    # ─────────────────────────────────────────────────────────────────────

    def add_reminder(self, text: str, seconds_from_now: int) -> str:
        try:
            import datetime as _dt
            remind_at = time.time() + seconds_from_now
            self.conn.execute(
                "INSERT INTO reminders (text, remind_at) VALUES (?,?)",
                (text, remind_at),
            )
            self.conn.commit()
            dt = _dt.datetime.fromtimestamp(remind_at).strftime("%H:%M %d.%m")
            return f"⏰ Напоминание на {dt}: {text}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def check_reminders(self) -> list[str]:
        """Возвращает сработавшие напоминания и помечает как выполненные."""
        try:
            now  = time.time()
            rows = self.conn.execute(
                "SELECT id, text FROM reminders WHERE remind_at<=? AND done=0",
                (now,),
            ).fetchall()
            fired = []
            for rid, text in rows:
                self.conn.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
                fired.append(f"⏰ НАПОМИНАНИЕ: {text}")
            if fired:
                self.conn.commit()
            return fired
        except Exception:
            return []

    # ─────────────────────────────────────────────────────────────────────
    # ГРАФ ЗНАНИЙ — алиасы для совместимости с core.py
    # ─────────────────────────────────────────────────────────────────────

    def add_graph_edge(self, subject: str, predicate: str, obj: str,
                       object_type: str = "", source: str = "user") -> str:
        """Алиас add_edge — совместимость с оригинальным memory.py."""
        return self.add_edge(subject, predicate, obj, object_type, source)

    def graph_report(self, limit: int = 20) -> str:
        """Алиас get_graph — совместимость с core.py."""
        return self.get_graph(limit)

    # ─────────────────────────────────────────────────────────────────────
    # RECALL / FORGET — совместимость с core.py
    # ─────────────────────────────────────────────────────────────────────

    def recall(self, key: str, category: str = "user") -> str | None:
        try:
            row = self.conn.execute(
                "SELECT value FROM facts WHERE category=? AND key=?",
                (category, key),
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def forget(self, key: str, category: str = "user") -> str:
        try:
            self.conn.execute(
                "DELETE FROM facts WHERE category=? AND key=?", (category, key)
            )
            self.conn.commit()
            return f"🗑️ Забыл: {key}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    # ─────────────────────────────────────────────────────────────────────
    # ИСТОРИЯ ДИАЛОГА
    # ─────────────────────────────────────────────────────────────────────

    def add_to_history(self, role: str, text: str) -> None:
        try:
            self.conn.execute(
                "INSERT INTO chat_history (role, text) VALUES (?, ?)", (role, text)
            )
            self.conn.commit()
        except Exception:
            pass

    def get_history(self, limit: int = 20) -> list[dict]:
        try:
            rows = self.conn.execute(
                "SELECT role, text, ts FROM chat_history ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"role": r, "text": t, "ts": ts} for r, t, ts in reversed(rows)]
        except Exception:
            return []

    # ─────────────────────────────────────────────────────────────────────
    # ГРАФ ЗНАНИЙ
    # ─────────────────────────────────────────────────────────────────────

    def add_edge(self, subject: str, predicate: str, obj: str,
                 obj_type: str = "", source: str = "user") -> str:
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO knowledge_edges "
                "(subject, predicate, object, object_type, source) VALUES (?,?,?,?,?)",
                (subject, predicate, obj, obj_type, source),
            )
            self.conn.commit()
            return f"✅ Связь: {subject} —[{predicate}]→ {obj}"
        except Exception as e:
            return f"❌ {e}"

    def get_graph(self, limit: int = 20) -> str:
        try:
            rows = self.conn.execute(
                "SELECT subject, predicate, object FROM knowledge_edges "
                "ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            if not rows:
                return "🕸️ Граф знаний пуст."
            lines = ["🕸️ ГРАФ ЗНАНИЙ:"]
            for s, p, o in rows:
                lines.append(f"  {s} —[{p}]→ {o}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ {e}"

    # ─────────────────────────────────────────────────────────────────────
    # ВСПОМОГАТЕЛЬНОЕ
    # ─────────────────────────────────────────────────────────────────────

    def attach_grist(self, grist) -> None:
        self.grist = grist

    def status(self) -> str:
        try:
            facts_count = self.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            notes_count = self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            hist_count  = self.conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
            vec_status  = self.vector.status() if self.vector else "⚠️ VectorStore: недоступен"
            return (
                f"🧠 ПАМЯТЬ АРГОСА:\n"
                f"  Фактов: {facts_count}\n"
                f"  Заметок: {notes_count}\n"
                f"  История диалогов: {hist_count}\n"
                f"  {vec_status}"
            )
        except Exception as e:
            return f"❌ Ошибка статуса памяти: {e}"
