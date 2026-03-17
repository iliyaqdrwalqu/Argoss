"""
browser_conduit.py — Модуль передачи запросов в браузер через буфер обмена.

Позволяет Аргосу отправлять текст в активное поле браузера через эмуляцию
клавиатуры и получать ответы через мониторинг буфера обмена.
"""

import time
import threading

from src.argos_logger import get_logger

log = get_logger("argos.browser_conduit")

try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    pyautogui = None
    PYAUTOGUI_OK = False

try:
    import pyperclip
    PYPERCLIP_OK = True
except ImportError:
    pyperclip = None
    PYPERCLIP_OK = False


class BrowserConduit:
    """Передаёт текст в браузер и принимает ответ через буфер обмена."""

    def __init__(self):
        self.last_clipboard = ""

    def send_to_browser(self, text: str, delay: int = 5) -> None:
        """Передаёт текст в браузер через эмуляцию клавиатуры.

        Args:
            text: Текст для отправки.
            delay: Время (в секундах) на переключение в окно браузера.
        """
        if not PYAUTOGUI_OK or not PYPERCLIP_OK:
            log.error(
                "pyautogui и/или pyperclip не установлены. "
                "Запусти: pip install pyautogui pyperclip"
            )
            return

        log.info(
            "⏳ У тебя есть %d секунд, чтобы открыть браузер и кликнуть в поле ввода...",
            delay,
        )
        print(
            f"⏳ У тебя есть {delay} секунд, чтобы открыть браузер и кликнуть в поле ввода..."
        )
        time.sleep(delay)

        # Копируем текст в буфер и вставляем, чтобы избежать проблем с раскладкой
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        pyautogui.press("enter")
        log.info("✅ Сообщение отправлено.")
        print("✅ Сообщение отправлено. Жду, когда ты скопируешь ответ...")

    def monitor_clipboard(self, callback) -> None:
        """Следит за буфером обмена и передаёт новое содержимое в callback.

        Как только пользователь нажимает «Copy» в браузере, Аргос
        подхватывает текст и вызывает callback(response).

        Args:
            callback: Функция, принимающая строку — скопированный ответ.
        """
        if not PYPERCLIP_OK:
            log.error(
                "pyperclip не установлен. Запусти: pip install pyperclip"
            )
            return

        self.last_clipboard = pyperclip.paste()

        def _check() -> None:
            while True:
                current = pyperclip.paste()
                if current != self.last_clipboard and current.strip():
                    self.last_clipboard = current
                    log.info("📥 Аргос получил ответ из браузера!")
                    print("\n📥 Аргос получил ответ из браузера!")
                    callback(current)
                    break
                time.sleep(1)

        threading.Thread(target=_check, daemon=True).start()


def handle_browser_query(core, query: str) -> str:
    """Формирует запрос и отправляет его в браузер; ждёт ответа из буфера.

    Args:
        core: Экземпляр ArgosCore.
        query: Текст запроса пользователя.

    Returns:
        Строка-подтверждение запуска цикла «отправка → ожидание ответа».
    """
    if not PYAUTOGUI_OK or not PYPERCLIP_OK:
        return (
            "❌ Модуль browser_conduit недоступен: "
            "установи зависимости командой: pip install pyautogui pyperclip"
        )

    conduit = BrowserConduit()

    # Формируем запрос от имени Аргоса
    full_request = f"Запрос через систему ARGOS OS:\n{query}"

    # Запускаем мониторинг ответа до отправки, чтобы не пропустить быстрый ответ
    conduit.monitor_clipboard(
        lambda response: core.execute_intent(
            f"запомни ответ искина: {response}", None, None
        )
    )

    # Отправляем в браузер
    conduit.send_to_browser(full_request)

    return "🌐 Запрос отправлен в браузер. Жду ответа через буфер обмена..."
