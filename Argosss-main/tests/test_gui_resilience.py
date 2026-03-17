import unittest
from pathlib import Path


class TestGuiResilience(unittest.TestCase):
    def test_gui_process_handles_core_exceptions(self):
        text = Path("src/interface/gui.py").read_text(encoding="utf-8")
        self.assertIn("except Exception as e:", text)
        self.assertIn("\"state\": \"ERROR\"", text)
        self.assertIn("❌ Ошибка выполнения команды:", text)

    def test_gui_response_handler_uses_safe_dict_access(self):
        text = Path("src/interface/gui.py").read_text(encoding="utf-8")
        self.assertIn("EMPTY_CORE_RESPONSE_TEXT = \"❌ Пустой ответ от ядра.\"", text)
        self.assertIn("payload = res if res is not None else {}", text)
        self.assertIn("state = payload.get(\"state\", \"ERROR\")", text)
        self.assertIn("answer = payload.get(\"answer\", self.EMPTY_CORE_RESPONSE_TEXT)", text)
