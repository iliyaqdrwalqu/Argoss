from types import SimpleNamespace

from src.core import ArgosCore


def test_setup_ai_ensures_ollama_before_core_continues(monkeypatch):
    """Ollama must be started even when GEMINI_API_KEY is absent."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    ensure_ollama_calls: list[str] = []
    dummy = SimpleNamespace(
        ai_mode="auto",
        model=SimpleNamespace(name="mock-model"),
        _ensure_ollama_running=lambda: ensure_ollama_calls.append("ensure"),
        _has_gigachat_config=lambda: False,
        _has_yandexgpt_config=lambda: False,
    )

    ArgosCore._setup_ai(dummy)

    assert ensure_ollama_calls == ["ensure"]


def test_setup_ai_ensures_ollama_when_gemini_key_present(monkeypatch):
    """Ollama must be started even when a Gemini key is configured.

    A key may be present but expired; Ollama should still start so it is
    available as a fallback without requiring a restart.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "fake-but-present-key")

    ensure_ollama_calls: list[str] = []
    dummy = SimpleNamespace(
        ai_mode="auto",
        model=None,
        _ensure_ollama_running=lambda: ensure_ollama_calls.append("ensure"),
        _has_gigachat_config=lambda: False,
        _has_yandexgpt_config=lambda: False,
    )

    ArgosCore._setup_ai(dummy)

    assert ensure_ollama_calls == ["ensure"], (
        "_ensure_ollama_running must be called regardless of Gemini key presence"
    )
