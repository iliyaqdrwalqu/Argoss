"""
memory.py — Долгосрочная память Аргоса
  Запоминает факты о пользователе, предпочтения, заметки.
    Хранится в SQLite + векторный индекс (RAG) + граф знаний.
"""
import os
import sqlite3
import time
import re
import hashlib
from src.argos_logger import get_logger
from src.knowledge.vector_store import ArgosVectorStore

log = get_logger("argos.memory")
DB_PATH = "data/memory.db"


class ArgosMemory:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.vector = ArgosVectorStore(path="data/chroma")
        self.grist = None
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
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                text     TEXT NOT NULL,
                remind_at REAL NOT NULL,
                done     INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                subject    TEXT NOT NULL,
                predicate  TEXT NOT NULL,
                object     TEXT NOT NULL,
                object_type TEXT DEFAULT '',
                source     TEXT DEFAULT 'memory',
                ts         TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(subject, predicate, object)
            );
        """)
        self._ensure_fact_columns()
        self.conn.commit()
        log.debug("Memory DB инициализирована.")

    def _ensure_fact_columns(self):
        migrations = [
            "ALTER TABLE facts ADD COLUMN utility_signal REAL DEFAULT 0",
            "ALTER TABLE facts ADD COLUMN expires_at REAL DEFAULT 0",
            "ALTER TABLE facts ADD COLUMN access_count INTEGER DEFAULT 0",
            "ALTER TABLE facts ADD COLUMN last_accessed REAL DEFAULT 0",
            "ALTER TABLE facts ADD COLUMN fingerprint TEXT DEFAULT ''",
        ]
        for sql in migrations:
            try:
                self.conn.execute(sql)
            except Exception:
                pass

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _fingerprint(self, category: str, key: str, value: str) -> str:
        base = f"{self._normalize_text(category)}|{self._normalize_text(key)}|{self._normalize_text(value)}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()

    def _default_signal(self, category: str, key: str, value: str) -> float:
        score = 1.0
        cat = (category or "").lower()
        k = (key or "").lower()
        v = (value or "")
        if cat in {"user", "system", "profile"}:
            score += 1.2
        if len(v) > 80:
            score += 0.3
        if any(token in k for token in ["ключ", "token", "api", "предпочт", "цель", "огранич"]):
            score += 0.8
        if cat == "noise":
            score = 0.2
        return round(score, 2)

    def _cleanup_noise(self, ttl_seconds: int = 72 * 3600):
        try:
            threshold = time.time() - ttl_seconds
            self.conn.execute(
                "DELETE FROM facts WHERE category='noise' AND ((expires_at > 0 AND expires_at <= ?) OR (expires_at = 0 AND strftime('%s', ts) <= ?))",
                (time.time(), threshold),
            )
            self.conn.commit()
        except Exception as e:
            log.warning("Memory noise cleanup: %s", e)

    def _warmup_vector_index(self):
        try:
            rows = self.conn.execute(
                "SELECT category, key, value, ts FROM facts ORDER BY id DESC LIMIT 1000"
            ).fetchall()
            for cat, key, val, ts in rows:
                text = f"[{cat}] {key}: {val}"
                doc_id = f"fact_{cat}_{key}".replace(" ", "_")
                self.vector.upsert(text, metadata={"kind": "fact", "category": cat, "ts": ts}, doc_id=doc_id)

            notes = self.conn.execute(
                "SELECT id, title, body, ts FROM notes ORDER BY id DESC LIMIT 500"
            ).fetchall()
            for note_id, title, body, ts in notes:
                text = f"Заметка: {title}\n{body}"
                self.vector.upsert(text, metadata={"kind": "note", "note_id": note_id, "ts": ts}, doc_id=f"note_{note_id}")
        except Exception as e:
            log.warning("Vector warmup: %s", e)

    def _index_text(self, text: str, metadata: dict | None = None, doc_id: str | None = None):
        if not text:
            return
        try:
            self.vector.upsert(text, metadata=metadata or {}, doc_id=doc_id)
        except Exception as e:
            log.warning("Vector index: %s", e)

    def attach_grist(self, grist):
        self.grist = grist

    def _mirror_to_grist(self, category: str, key: str, value: str):
        if not self.grist or not getattr(self.grist, "_configured", False):
            return
        try:
            self.grist.save(f"memory:{category}:{key}", value)
        except Exception as e:
            log.warning("Grist mirror memory: %s", e)

    # ── ФАКТЫ ──────────────────────────────────────────────
    def remember(self, key: str, value: str, category: str = "user", ttl_sec: int | None = None) -> str:
        """Запомнить факт. 'аргос, запомни: я люблю Python'"""
        norm_key = self._normalize_text(key)
        norm_val = self._normalize_text(value)
        if not norm_key or not norm_val:
            return "❌ Нечего запоминать: пустой ключ или значение."

        fp = self._fingerprint(category, key, value)
        self._cleanup_noise()

        dup = self.conn.execute(
            "SELECT id, value FROM facts WHERE category=? AND key=?",
            (category, key),
        ).fetchone()
        if dup and self._normalize_text(dup[1]) == norm_val:
            self.conn.execute(
                "UPDATE facts SET access_count=access_count+1, last_accessed=? WHERE id=?",
                (time.time(), dup[0]),
            )
            self.conn.commit()
            return f"ℹ️ Уже в памяти: {key} → {value}"

        expires_at = float(time.time() + ttl_sec) if ttl_sec and ttl_sec > 0 else 0.0
        signal = self._default_signal(category, key, value)
        self.conn.execute(
            "INSERT INTO facts (category, key, value, utility_signal, expires_at, access_count, last_accessed, fingerprint) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(category,key) DO UPDATE SET "
            "value=excluded.value, ts=datetime('now','localtime'), utility_signal=excluded.utility_signal, "
            "expires_at=excluded.expires_at, access_count=facts.access_count+1, last_accessed=excluded.last_accessed, fingerprint=excluded.fingerprint",
            (category, key, value, signal, expires_at, 1, time.time(), fp)
        )
        self.conn.commit()
        self._index_text(
            f"[{category}] {key}: {value}",
            metadata={"kind": "fact", "category": category, "key": key},
            doc_id=f"fact_{category}_{key}".replace(" ", "_")
        )
        self._extract_graph_from_fact(key, value, category=category)
        self._mirror_to_grist(category, key, value)
        log.info("Запомнил [%s] %s = %s", category, key, value)
        return f"✅ Запомнил: {key} → {value}"

    def recall(self, key: str, category: str = "user") -> str | None:
        row = self.conn.execute(
            "SELECT id, value FROM facts WHERE category=? AND key=?", (category, key)
        ).fetchone()
        if not row:
            return None
        self.conn.execute(
            "UPDATE facts SET access_count=access_count+1, utility_signal=utility_signal+0.1, last_accessed=? WHERE id=?",
            (time.time(), row[0]),
        )
        self.conn.commit()
        return row[1]

    def forget(self, key: str, category: str = "user") -> str:
        self.conn.execute("DELETE FROM facts WHERE category=? AND key=?", (category, key))
        self.conn.commit()
        return f"🗑️ Удалено из памяти: {key}"

    def search_semantic(self, query: str, top_k: int = 5) -> list[dict]:
        try:
            return self.vector.search(query, top_k=top_k)
        except Exception as e:
            log.warning("RAG search: %s", e)
            return []

    def get_rag_context(self, query: str, top_k: int = 4) -> str:
        hits = self.search_semantic(query, top_k=top_k)
        if not hits:
            return ""
        lines = ["[RAG: релевантные воспоминания]"]
        for item in hits:
            text = (item.get("text") or "").strip().replace("\n", " ")
            score = float(item.get("score", 0.0))
            if not text:
                continue
            lines.append(f"  ({score:.2f}) {text[:220]}")
        return "\n".join(lines)

    def get_all_facts(self, category: str = None) -> list:
        self._cleanup_noise()
        if category:
            return self.conn.execute(
                "SELECT category, key, value, ts FROM facts "
                "WHERE category=? AND (expires_at=0 OR expires_at>?) "
                "ORDER BY utility_signal DESC, ts DESC",
                (category, time.time())
            ).fetchall()
        return self.conn.execute(
            "SELECT category, key, value, ts FROM facts "
            "WHERE (expires_at=0 OR expires_at>?) "
            "ORDER BY utility_signal DESC, category, key",
            (time.time(),)
        ).fetchall()

    def get_context(self) -> str:
        """Возвращает строку контекста для вставки в ИИ-запрос."""
        facts = self.get_all_facts()
        if not facts:
            return ""
        lines = ["Известные факты о пользователе и системе:"]
        for cat, key, val, _ in facts[:60]:
            lines.append(f"  [{cat}] {key}: {val}")
        return "\n".join(lines)

    def log_dialogue(self, role: str, message: str, state: str = ""):
        text = (message or "").strip()
        if not text:
            return
        text = text[:2000]
        self._index_text(
            f"[{role}] {text}",
            metadata={"kind": "dialogue", "role": role, "state": state},
            doc_id=None
        )

    def format_memory(self) -> str:
        facts = self.get_all_facts()
        edges_count = self.conn.execute("SELECT COUNT(*) FROM knowledge_edges").fetchone()[0]
        lines = ["🧠 ДОЛГОСРОЧНАЯ ПАМЯТЬ АРГОСА:"]
        lines.append(f"  • Vector store: {self.vector.status()}")
        lines.append(f"  • Граф связей: {edges_count} ребер")
        if not facts:
            lines.append("  • Фактов пока нет")
            return "\n".join(lines)
        prev_cat = None
        for cat, key, val, ts in facts:
            if cat != prev_cat:
                lines.append(f"\n  [{cat.upper()}]")
                prev_cat = cat
            lines.append(f"    • {key}: {val}  ({ts[:16]})")
        return "\n".join(lines)

    # ── ЗАМЕТКИ ────────────────────────────────────────────
    def add_note(self, title: str, body: str) -> str:
        self.conn.execute(
            "INSERT INTO notes (title, body) VALUES (?,?)", (title, body)
        )
        self.conn.commit()
        row = self.conn.execute("SELECT last_insert_rowid()")
        note_id = row.fetchone()[0]
        self._index_text(
            f"Заметка: {title}\n{body}",
            metadata={"kind": "note", "note_id": note_id, "title": title},
            doc_id=f"note_{note_id}"
        )
        return f"📝 Заметка сохранена: '{title}'"

    def get_notes(self, limit: int = 10) -> str:
        rows = self.conn.execute(
            "SELECT id, title, ts FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        if not rows:
            return "📭 Заметок нет."
        lines = [f"📝 ЗАМЕТКИ ({len(rows)}):"]
        for rid, title, ts in rows:
            lines.append(f"  #{rid} [{ts[:16]}] {title}")
        return "\n".join(lines)

    def read_note(self, note_id: int) -> str:
        row = self.conn.execute(
            "SELECT title, body, ts FROM notes WHERE id=?", (note_id,)
        ).fetchone()
        if not row:
            return f"❌ Заметка #{note_id} не найдена."
        title, body, ts = row
        return f"📝 #{note_id} [{ts[:16]}] {title}\n\n{body}"

    def delete_note(self, note_id: int) -> str:
        self.conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
        self.conn.commit()
        return f"🗑️ Заметка #{note_id} удалена."

    # ── НАПОМИНАНИЯ ────────────────────────────────────────
    def add_reminder(self, text: str, seconds_from_now: int) -> str:
        remind_at = time.time() + seconds_from_now
        self.conn.execute(
            "INSERT INTO reminders (text, remind_at) VALUES (?,?)", (text, remind_at)
        )
        self.conn.commit()
        import datetime
        dt = datetime.datetime.fromtimestamp(remind_at).strftime("%H:%M %d.%m")
        return f"⏰ Напоминание установлено на {dt}: {text}"

    def check_reminders(self) -> list[str]:
        now  = time.time()
        rows = self.conn.execute(
            "SELECT id, text FROM reminders WHERE remind_at<=? AND done=0", (now,)
        ).fetchall()
        fired = []
        for rid, text in rows:
            self.conn.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
            fired.append(f"⏰ НАПОМИНАНИЕ: {text}")
        if fired:
            self.conn.commit()
        return fired

    def parse_and_remember(self, text: str) -> str:
        """'аргос, запомни что я люблю Python' → сохраняет факт"""
        original = (text or "").strip()
        t = original.lower()

        pet_match = re.search(r"(?:мой|моя)\s+кот\s*[—\-:]?\s*([A-Za-zА-Яа-я0-9_\-]+)", original, re.IGNORECASE)
        if pet_match:
            pet_name = pet_match.group(1).strip()
            self.remember("pet_name", pet_name, category="user")
            self.add_graph_edge("User", "has_pet", f"Cat:{pet_name}", object_type="Cat", source="nlp")
            return f"✅ Запомнил: ваш кот — {pet_name}. Связь добавлена в граф знаний."

        for pref in ["запомни что ", "запомни: ", "запомни ", "я "]:
            if t.startswith(pref):
                rest = original[len(pref):]
                if ":" in rest:
                    key, val = rest.split(":", 1)
                    return self.remember(key.strip(), val.strip())
                return self.remember("факт", rest.strip())
        return self.remember("факт", original)

    # ── ГРАФ ЗНАНИЙ ───────────────────────────────────────
    def add_graph_edge(self, subject: str, predicate: str, obj: str,
                       object_type: str = "", source: str = "memory") -> str:
        self.conn.execute(
            "INSERT OR IGNORE INTO knowledge_edges (subject, predicate, object, object_type, source) VALUES (?,?,?,?,?)",
            (subject.strip(), predicate.strip(), obj.strip(), object_type.strip(), source.strip())
        )
        self.conn.commit()
        self._index_text(
            f"GRAPH: {subject} -[{predicate}]-> {obj}",
            metadata={"kind": "graph", "subject": subject, "predicate": predicate, "object": obj, "object_type": object_type}
        )
        return f"🔗 Связь добавлена: {subject} -[{predicate}]-> {obj}"

    def _extract_graph_from_fact(self, key: str, value: str, category: str = "user"):
        key_l = (key or "").strip().lower()
        val = (value or "").strip()
        if not key_l or not val:
            return

        if key_l in {"кот", "мой кот", "pet", "pet_name", "питомец"}:
            self.add_graph_edge("User", "has_pet", f"Cat:{val}", object_type="Cat", source="fact")
            return

        self.add_graph_edge("User", f"has_{key_l}", val, object_type="Fact", source=category)

    def graph_report(self, limit: int = 20) -> str:
        rows = self.conn.execute(
            "SELECT subject, predicate, object, object_type, ts FROM knowledge_edges ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        if not rows:
            return "🕸️ Граф знаний пуст."

        lines = [f"🕸️ ГРАФ ЗНАНИЙ ({len(rows)}):"]
        for s, p, o, obj_t, ts in rows:
            ot = f" [{obj_t}]" if obj_t else ""
            lines.append(f"  • {s} -[{p}]-> {o}{ot} ({ts[:16]})")
        return "\n".join(lines)

    def close(self):
        self.conn.close()
