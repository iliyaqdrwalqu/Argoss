"""
tests/test_browser_conduit.py — Автотесты модуля BrowserConduit.

Внешние зависимости (pyautogui, pyperclip, time.sleep) мокируются —
тесты не зависят от рабочего стола или системного буфера обмена.
Запуск: python -m pytest tests/test_browser_conduit.py -v
"""

import sys
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Мок-модули для pyautogui / pyperclip, если не установлены
# ---------------------------------------------------------------------------
import importlib

_pyautogui_mock = MagicMock()
_pyperclip_mock = MagicMock()

# Убеждаемся, что модули подменены до импорта browser_conduit
sys.modules.setdefault("pyautogui", _pyautogui_mock)
sys.modules.setdefault("pyperclip", _pyperclip_mock)

# Теперь безопасно импортировать
import src.skills.browser_conduit as bc_module
from src.skills.browser_conduit import BrowserConduit, handle_browser_query


class TestBrowserConduitSendToBrowser(unittest.TestCase):
    """Тесты метода BrowserConduit.send_to_browser."""

    def setUp(self):
        self.conduit = BrowserConduit()
        # Сбрасываем счётчики вызовов между тестами
        _pyautogui_mock.reset_mock()
        _pyperclip_mock.reset_mock()

    def _patch_deps(self):
        """Контекстный менеджер: помечаем оба флага как доступные."""
        return patch.multiple(
            bc_module,
            PYAUTOGUI_OK=True,
            PYPERCLIP_OK=True,
        )

    def test_copies_text_to_clipboard(self):
        """send_to_browser должен скопировать текст в буфер обмена."""
        with self._patch_deps(), patch("time.sleep"):
            self.conduit.send_to_browser("привет", delay=0)
        _pyperclip_mock.copy.assert_called_once_with("привет")

    def test_pastes_with_ctrl_v_and_enter(self):
        """send_to_browser должен эмулировать Ctrl+V и Enter."""
        with self._patch_deps(), patch("time.sleep"):
            self.conduit.send_to_browser("тест", delay=0)
        _pyautogui_mock.hotkey.assert_called_once_with("ctrl", "v")
        _pyautogui_mock.press.assert_called_once_with("enter")

    def test_sleep_called_with_correct_delay(self):
        """send_to_browser должен выждать заданное количество секунд."""
        with self._patch_deps(), patch("time.sleep") as mock_sleep:
            self.conduit.send_to_browser("тест", delay=3)
        mock_sleep.assert_called_once_with(3)

    def test_no_action_when_pyautogui_missing(self):
        """Если pyautogui недоступен, действие не выполняется."""
        with patch.multiple(bc_module, PYAUTOGUI_OK=False, PYPERCLIP_OK=True):
            self.conduit.send_to_browser("тест", delay=0)
        _pyautogui_mock.hotkey.assert_not_called()

    def test_no_action_when_pyperclip_missing(self):
        """Если pyperclip недоступен, действие не выполняется."""
        with patch.multiple(bc_module, PYAUTOGUI_OK=True, PYPERCLIP_OK=False):
            self.conduit.send_to_browser("тест", delay=0)
        _pyperclip_mock.copy.assert_not_called()


class TestBrowserConduitMonitorClipboard(unittest.TestCase):
    """Тесты метода BrowserConduit.monitor_clipboard."""

    def setUp(self):
        self.conduit = BrowserConduit()
        _pyperclip_mock.reset_mock()

    def test_callback_called_on_new_clipboard_content(self):
        """Callback должен вызываться, когда содержимое буфера изменилось."""
        _pyperclip_mock.paste.side_effect = ["старый текст", "старый текст", "новый ответ"]

        done = threading.Event()
        callback = MagicMock(side_effect=lambda _: done.set())
        with patch.multiple(bc_module, PYPERCLIP_OK=True), \
             patch("src.skills.browser_conduit.time") as mock_time:
            # time.sleep — no-op, time module available to thread
            mock_time.sleep = MagicMock()
            self.conduit.monitor_clipboard(callback)
            done.wait(timeout=2.0)

        callback.assert_called_once_with("новый ответ")

    def test_callback_not_called_when_clipboard_unchanged(self):
        """Callback не должен вызываться, если буфер не изменился (быстрый стоп)."""
        event = threading.Event()
        _pyperclip_mock.paste.side_effect = lambda: (
            event.set() or "тот же текст"  # стабильный возврат одного значения
        )

        callback = MagicMock()
        with patch.multiple(bc_module, PYPERCLIP_OK=True), \
             patch("time.sleep", return_value=None):
            self.conduit.monitor_clipboard(callback)
            # Позволяем циклу прокрутиться несколько раз
            event.wait(timeout=0.3)
            time.sleep(0.1)

        callback.assert_not_called()

    def test_no_action_when_pyperclip_missing(self):
        """Если pyperclip недоступен, поток не запускается и callback не вызывается."""
        callback = MagicMock()
        initial_threads = threading.active_count()
        with patch.multiple(bc_module, PYPERCLIP_OK=False):
            self.conduit.monitor_clipboard(callback)
        # Количество потоков не должно вырасти
        self.assertEqual(threading.active_count(), initial_threads)
        callback.assert_not_called()


class TestHandleBrowserQuery(unittest.TestCase):
    """Тесты функции-обёртки handle_browser_query."""

    def setUp(self):
        self.core = MagicMock()
        _pyautogui_mock.reset_mock()
        _pyperclip_mock.reset_mock()

    def test_returns_confirmation_string(self):
        """handle_browser_query должна вернуть строку-подтверждение."""
        with patch.multiple(bc_module, PYAUTOGUI_OK=True, PYPERCLIP_OK=True), \
             patch("time.sleep"), \
             patch.object(BrowserConduit, "monitor_clipboard"), \
             patch.object(BrowserConduit, "send_to_browser"):
            result = handle_browser_query(self.core, "Какой курс доллара?")
        self.assertIn("браузер", result.lower())

    def test_returns_error_when_deps_missing(self):
        """При отсутствии зависимостей возвращает сообщение об ошибке."""
        with patch.multiple(bc_module, PYAUTOGUI_OK=False, PYPERCLIP_OK=False):
            result = handle_browser_query(self.core, "тест")
        self.assertIn("❌", result)
        self.assertIn("pip install", result)

    def test_full_request_contains_query(self):
        """Текст запроса должен попасть в send_to_browser."""
        sent_texts = []

        def fake_send(self_arg, text, **kwargs):
            sent_texts.append(text)

        with patch.multiple(bc_module, PYAUTOGUI_OK=True, PYPERCLIP_OK=True), \
             patch("time.sleep"), \
             patch.object(BrowserConduit, "monitor_clipboard"), \
             patch.object(BrowserConduit, "send_to_browser", fake_send):
            handle_browser_query(self.core, "напиши стих")

        self.assertTrue(any("напиши стих" in t for t in sent_texts))

    def test_monitor_called_before_send(self):
        """Мониторинг буфера должен стартовать до отправки текста в браузер."""
        call_order = []

        def fake_monitor(self_arg, cb):
            call_order.append("monitor")

        def fake_send(self_arg, text, **kwargs):
            call_order.append("send")

        with patch.multiple(bc_module, PYAUTOGUI_OK=True, PYPERCLIP_OK=True), \
             patch("time.sleep"), \
             patch.object(BrowserConduit, "monitor_clipboard", fake_monitor), \
             patch.object(BrowserConduit, "send_to_browser", fake_send):
            handle_browser_query(self.core, "тест порядка")

        self.assertEqual(call_order, ["monitor", "send"])


if __name__ == "__main__":
    unittest.main()
