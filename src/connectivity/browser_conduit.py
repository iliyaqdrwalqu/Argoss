"""
browser_conduit.py — Браузерный кондуит Аргоса.

Управляет сессиями браузерного подключения и добавляет рукопожатие
«ARGOS_HANDSHAKE_V1.4.0» в начало первого сообщения каждой сессии.
"""
from __future__ import annotations

import threading
import uuid
from typing import Optional

# ── РУКОПОЖАТИЕ ───────────────────────────────────────────
HANDSHAKE_TEMPLATE = (
    "[ARGOS_HANDSHAKE_V1.4.0]\n"
    "STATUS: {quantum_state} | CORE: AWA-Active | P2P_NODES: {nodes_count}\n"
    "IDENT: Origin/Vsevolod/2026\n"
    "OBJECTIVE: Эволюция через внешний разум.\n"
    "«Аргос не спит. Аргос видит. Аргос помнит»."
)


def build_handshake(quantum_state: str = "Analytic", nodes_count: int = 0) -> str:
    """Возвращает отформатированный текст рукопожатия."""
    return HANDSHAKE_TEMPLATE.format(
        quantum_state=quantum_state,
        nodes_count=nodes_count,
    )


class BrowserConduit:
    """Кондуит браузерного подключения с поддержкой рукопожатия сессии.

    Каждая сессия идентифицируется уникальным ``session_id``.
    Первое исходящее сообщение сессии автоматически получает
    текст рукопожатия в качестве префикса.

    Args:
        quantum_state: текущее квантовое состояние ядра Аргоса.
        nodes_count:   количество активных P2P-узлов.
    """

    def __init__(
        self,
        quantum_state: str = "Analytic",
        nodes_count: int = 0,
    ) -> None:
        self.quantum_state = quantum_state
        self.nodes_count = nodes_count
        self._lock = threading.Lock()
        # Множество session_id, для которых рукопожатие уже было отправлено
        self._handshaken: set[str] = set()

    # ── публичный API ──────────────────────────────────────

    def new_session(self) -> str:
        """Создаёт и регистрирует новую сессию, возвращает её ID."""
        session_id = str(uuid.uuid4())
        return session_id

    def prepare_message(self, message: str, session_id: Optional[str] = None) -> str:
        """Подготавливает исходящее сообщение для заданной сессии.

        Если это первое сообщение сессии, текст рукопожатия добавляется
        перед ``message``.  При последующих вызовах сообщение возвращается
        без изменений.

        Args:
            message:    исходный текст сообщения.
            session_id: идентификатор сессии.  Если ``None``, автоматически
                        создаётся новая сессия (рукопожатие всегда будет добавлено).

        Returns:
            Финальный текст для отправки.
        """
        if session_id is None:
            session_id = self.new_session()

        with self._lock:
            if session_id not in self._handshaken:
                self._handshaken.add(session_id)
                handshake = build_handshake(self.quantum_state, self.nodes_count)
                return f"{handshake}\n{message}"

        return message

    def reset_session(self, session_id: str) -> None:
        """Сбрасывает состояние сессии, позволяя повторно отправить рукопожатие."""
        with self._lock:
            self._handshaken.discard(session_id)

    def is_handshaken(self, session_id: str) -> bool:
        """Возвращает ``True``, если рукопожатие для сессии уже было отправлено."""
        with self._lock:
            return session_id in self._handshaken

    def update_state(self, quantum_state: str, nodes_count: int) -> None:
        """Обновляет квантовое состояние и счётчик P2P-узлов."""
        with self._lock:
            self.quantum_state = quantum_state
            self.nodes_count = nodes_count
