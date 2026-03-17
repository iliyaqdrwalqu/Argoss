import unittest
from pathlib import Path


class TestProviderErrorBackoffWiring(unittest.TestCase):
    def test_core_has_provider_temporary_disable_mechanism(self):
        text = Path("src/core.py").read_text(encoding="utf-8")
        self.assertIn("def _is_provider_temporarily_disabled(self, provider_name: str) -> bool:", text)
        self.assertIn("def _disable_provider_temporarily(self, provider_name: str, reason: str) -> None:", text)
        self.assertIn("ARGOS_PROVIDER_FAILURE_COOLDOWN", text)
        self.assertIn("self._provider_disabled_permanent", text)
        self.assertIn("dict[str, str]", text)

    def test_cloud_provider_errors_trigger_temporary_disable(self):
        text = Path("src/core.py").read_text(encoding="utf-8")
        self.assertIn("self._disable_provider_temporarily(\"Gemini\", \"некорректный/просроченный API ключ\")", text)
        self.assertIn("if response.status_code in (401, 403):", text)
        self.assertIn("self._disable_provider_temporarily(\"GigaChat\", f\"ошибка авторизации HTTP {response.status_code}\")", text)
        self.assertIn("self._disable_provider_temporarily(\"YandexGPT\", f\"ошибка авторизации HTTP {response.status_code}\")", text)

    def test_auto_mode_skips_temporarily_disabled_clouds(self):
        text = Path("src/core.py").read_text(encoding="utf-8")
        self.assertIn("if self.model and not self._is_provider_temporarily_disabled(\"Gemini\"):", text)
        self.assertIn("if self._has_gigachat_config() and not self._is_provider_temporarily_disabled(\"GigaChat\"):", text)
        self.assertIn("if self._has_yandexgpt_config() and not self._is_provider_temporarily_disabled(\"YandexGPT\"):", text)

    def test_tts_runtime_is_serialized_with_lock(self):
        text = Path("src/core.py").read_text(encoding="utf-8")
        self.assertIn("self._tts_lock = threading.Lock()", text)
        self.assertIn("with self._tts_lock:", text)
