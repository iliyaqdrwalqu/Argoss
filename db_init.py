"""
db_init.py — Инициализация базы данных Аргоса (SQLite)
  Хранит: историю чатов, логи команд, навыки, геопозиции
"""
import sqlite3
import os
import threading

DB_PATH = "data/argos.db"

def init_db() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    # История диалогов
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now','localtime')),
            role      TEXT NOT NULL,          -- 'user' | 'argos'
            state     TEXT,                   -- квантовое состояние
            message   TEXT NOT NULL
        )
    """)

    # Лог системных команд
    c.execute("""
        CREATE TABLE IF NOT EXISTS command_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now','localtime')),
            command   TEXT NOT NULL,
            result    TEXT,
            source    TEXT DEFAULT 'gui'       -- 'gui' | 'telegram' | 'voice'
        )
    """)

    # Реестр навыков
    c.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            active      INTEGER DEFAULT 1
        )
    """)

    # Геопозиции (история локаций)
    c.execute("""
        CREATE TABLE IF NOT EXISTS geo_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now','localtime')),
            city      TEXT,
            country   TEXT,
            isp       TEXT,
            ip        TEXT
        )
    """)

    # Крипто-алерты
    c.execute("""
        CREATE TABLE IF NOT EXISTS crypto_alerts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now','localtime')),
            coin      TEXT,
            price     REAL,
            change    REAL,
            alerted   INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    print(f"[DB]: База данных инициализирована → {DB_PATH}")
    return conn


class ArgosDB:
    """Обёртка для работы с БД из любого модуля."""

    def __init__(self):
        self.conn = init_db()
        self._lock = threading.RLock()

    def _execute(self, query: str, params: tuple = (), commit: bool = False):
        with self._lock:
            cur = self.conn.execute(query, params)
            if commit:
                self.conn.commit()
            return cur

    def log_chat(self, role: str, message: str, state: str = None):
        self._execute(
            "INSERT INTO chat_history (role, state, message) VALUES (?,?,?)",
            (role, state, message),
            commit=True,
        )

    def log_command(self, command: str, result: str, source: str = "gui"):
        self._execute(
            "INSERT INTO command_log (command, result, source) VALUES (?,?,?)",
            (command, result, source),
            commit=True,
        )

    def log_geo(self, city: str, country: str, isp: str = "", ip: str = ""):
        self._execute(
            "INSERT INTO geo_log (city, country, isp, ip) VALUES (?,?,?,?)",
            (city, country, isp, ip),
            commit=True,
        )

    def get_history(self, limit: int = 20) -> list:
        cur = self._execute(
            "SELECT timestamp, role, state, message FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()

    def get_command_log(self, limit: int = 20) -> list:
        cur = self._execute(
            "SELECT timestamp, command, result, source FROM command_log ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()

    def search_history(self, query: str) -> list:
        cur = self._execute(
            "SELECT timestamp, role, message FROM chat_history WHERE message LIKE ? ORDER BY id DESC LIMIT 10",
            (f"%{query}%",)
        )
        return cur.fetchall()

    def format_history(self, limit: int = 10) -> str:
        rows = self.get_history(limit)
        if not rows:
            return "📭 История пуста."
        lines = [f"📜 ИСТОРИЯ (последние {limit}):"]
        for ts, role, state, msg in reversed(rows):
            icon = "👤" if role == "user" else "👁️"
            st   = f"[{state}] " if state else ""
            lines.append(f"  {ts} {icon} {st}{msg[:80]}{'...' if len(msg) > 80 else ''}")
        return "\n".join(lines)

    def close(self):
        with self._lock:
            self.conn.close()


if __name__ == "__main__":
    db = ArgosDB()
    db.log_chat("argos", "Система инициализирована.", "Analytic")
    print(db.format_history())
    db.close()
