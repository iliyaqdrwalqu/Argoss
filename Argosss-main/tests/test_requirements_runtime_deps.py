import unittest
from pathlib import Path

QUICKSTART_FILES = ("quickstart.md", "docs/user-guide/quickstart.md")


class TestRequirementsRuntimeDeps(unittest.TestCase):
    def test_requirements_include_critical_ai_and_ui_packages(self):
        text = Path("requirements.txt").read_text(encoding="utf-8")
        for dep in (
            "google-genai>=",
            'ibm-watsonx-ai>=1.3.42,<1.4.0; python_version < "3.11"',
            'ibm-watsonx-ai>=1.4.2; python_version >= "3.11"',
            "ollama>=",
            "streamlit>=",
            "faster-whisper>=",
            "customtkinter>=",
        ):
            self.assertIn(dep, text)

    def test_build_scaffold_includes_required_dependencies(self):
        text = Path("build.py").read_text(encoding="utf-8")
        for dep in (
            "google-genai>=",
            'ibm-watsonx-ai>=1.3.42,<1.4.0; python_version < "3.11"',
            'ibm-watsonx-ai>=1.4.2; python_version >= "3.11"',
            "ollama>=",
        ):
            self.assertIn(dep, text)

    def test_quickstart_includes_ollama_installation(self):
        expected = "curl -fsSL https://ollama.com/install.sh | sh"
        warning = "рекомендуется сначала просмотреть скрипт install.sh"
        for file_path in QUICKSTART_FILES:
            file = Path(file_path)
            self.assertTrue(file.exists(), f"Quickstart file is missing: {file_path}")
            content = file.read_text(encoding="utf-8")
            self.assertIn(
                expected,
                content,
                f"Ollama installation command not found in {file_path}",
            )
            self.assertIn(
                warning,
                content,
                f"Ollama installation safety warning not found in {file_path}",
            )
