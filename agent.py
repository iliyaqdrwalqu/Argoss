"""
src/agent.py — Автономный агент ARGOS (цепочки задач).

ПАТЧ [FIX-CIRCULAR-SRC]:
  Убран прямой топ-левел импорт ArgosCore / src.core.
  Теперь используется TYPE_CHECKING + строковая аннотация,
  чтобы разорвать цикл:
      src.core → src.agent → src.core  (цикл!)

  ArgosCore передаётся как аргумент __init__(core=...) —
  никакого импорта на уровне модуля не нужно.
"""
from __future__ import annotations

import re
import threading
import time
from typing import TYPE_CHECKING

from src.argos_logger import get_logger

if TYPE_CHECKING:
    # Импортируется ТОЛЬКО при проверке типов (mypy/pyright),
    # НЕ при выполнении — цикл разорван.
    from src.core import ArgosCore

log = get_logger("argos.agent")


class ArgosAgent:
    """Автономный агент: выполняет цепочки задач последовательно."""

    def __init__(self, core: "ArgosCore"):  # строковая аннотация — не импорт
        self.core = core
        self._running = False
        self._thread: threading.Thread | None = None
        self._current_chain: list[str] = []
        self._results: list[str] = []
        self._stop_event = threading.Event()

    # ─────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────

    def run_chain(self, commands: list[str]) -> str:
        """Запустить цепочку команд в фоновом потоке."""
        if self._running:
            return "⚠️ Агент уже выполняет задачу. Дождись завершения или останови его."

        self._current_chain = list(commands)
        self._results = []
        self._stop_event.clear()
        self._running = True

        self._thread = threading.Thread(
            target=self._execute_chain,
            daemon=True,
            name="ArgosAgent",
        )
        self._thread.start()
        return f"🤖 Агент запущен: {len(commands)} задач в очереди."

    def stop(self) -> str:
        """Остановить выполнение цепочки."""
        if not self._running:
            return "ℹ️ Агент не активен."
        self._stop_event.set()
        self._running = False
        return "🛑 Агент остановлен."

    def status(self) -> str:
        """Краткий статус агента."""
        if not self._running:
            last = f" | Последний результат: {self._results[-1][:80]}" if self._results else ""
            return f"🤖 Агент: ожидание{last}"
        remaining = len(self._current_chain)
        done = len(self._results)
        return (
            f"🤖 Агент: активен | Выполнено: {done} | "
            f"Осталось: {remaining} | "
            f"Текущая: {self._current_chain[0][:40] if self._current_chain else '—'}"
        )

    def report(self) -> str:
        """Полный отчёт о выполненных задачах."""
        if not self._results:
            return "🤖 Агент: нет результатов."
        lines = ["🤖 ОТЧЁТ АГЕНТА:"]
        for i, r in enumerate(self._results, 1):
            lines.append(f"  {i}. {r[:120]}")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Внутренняя логика
    # ─────────────────────────────────────────────────────────────────────

    def _execute_chain(self) -> None:
        log.info("Агент: начало цепочки (%d задач)", len(self._current_chain))
        while self._current_chain and not self._stop_event.is_set():
            cmd = self._current_chain.pop(0)
            log.info("Агент: выполняю → %s", cmd)
            try:
                result = self.core.process(cmd)
                answer = (
                    result.get("answer", str(result))
                    if isinstance(result, dict)
                    else str(result)
                )
                self._results.append(f"[{cmd[:30]}] {answer[:200]}")
                log.info("Агент: готово → %s", answer[:60])
            except Exception as e:
                err = f"[{cmd[:30]}] ❌ {e}"
                self._results.append(err)
                log.warning("Агент: ошибка → %s", e)

            # Небольшая пауза между задачами
            if self._current_chain and not self._stop_event.is_set():
                time.sleep(0.5)

        self._running = False
        log.info("Агент: цепочка завершена (%d результатов)", len(self._results))

    # ─────────────────────────────────────────────────────────────────────
    # Парсинг цепочек из текста пользователя
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def parse_chain(text: str) -> list[str]:
        """
        Разбирает текст пользователя на список команд.

        Поддерживает форматы:
          «статус → затем крипто → потом телеграм»
          «1. статус 2. крипто 3. телеграм»
          «статус; крипто; телеграм»
        """
        # Разделители: →, затем, потом, ;, numbered list
        parts = re.split(r"→|затем|потом|;|\d+\.", text, flags=re.IGNORECASE)
        commands = [p.strip() for p in parts if p.strip()]
        return commands
