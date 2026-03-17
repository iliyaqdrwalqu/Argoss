import sys
import builtins

from src.interface import streamlit_dashboard
from src.quantum.logic import ArgosQuantum
from src.skills.crypto_monitor import CryptoSentinel


def test_crypto_sentinel_loop_uses_bot_send(monkeypatch):
    sent_messages = []

    class DummyBot:
        def send(self, msg):
            sent_messages.append(msg)

    sentinel = CryptoSentinel(telegram_bot=DummyBot())
    monkeypatch.setattr(sentinel, "check", lambda: ["alert-message"])

    def fake_sleep(_):
        sentinel._running = False

    monkeypatch.setattr("src.skills.crypto_monitor.skill.time.sleep", fake_sleep)

    class ImmediateThread:
        def __init__(self, target, daemon=True):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("src.skills.crypto_monitor.skill.threading.Thread", ImmediateThread)

    sentinel.start_loop(interval_sec=1)
    assert sent_messages == ["alert-message"]


def test_crypto_sentinel_loop_uses_telegram_app_bot(monkeypatch):
    sent_messages = []

    class DummyAppBot:
        async def send_message(self, chat_id, text):
            sent_messages.append((chat_id, text))

    class DummyBot:
        user_id = "12345"
        app = type("DummyApp", (), {"bot": DummyAppBot()})()

    sentinel = CryptoSentinel(telegram_bot=DummyBot())
    monkeypatch.setattr(sentinel, "check", lambda: ["alert-message"])

    def fake_sleep(_):
        sentinel._running = False

    monkeypatch.setattr("src.skills.crypto_monitor.skill.time.sleep", fake_sleep)

    class ImmediateThread:
        def __init__(self, target, daemon=True):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("src.skills.crypto_monitor.skill.threading.Thread", ImmediateThread)

    sentinel.start_loop(interval_sec=1)
    assert sent_messages == [("12345", "alert-message")]


def test_quantum_updates_user_activity_from_detector(monkeypatch):
    quantum = ArgosQuantum()
    monkeypatch.setattr(quantum, "_effective_metric", lambda *_: 0.0)
    monkeypatch.setattr(quantum, "_is_user_active", lambda: False)
    quantum._update_evidence()
    assert quantum.evidence["user_active"] is False


def test_streamlit_run_starts_subprocess(monkeypatch):
    launched = []

    monkeypatch.setitem(sys.modules, "streamlit", object())
    monkeypatch.setattr(
        streamlit_dashboard.subprocess,
        "Popen",
        lambda cmd: (launched.append(cmd) or type("Proc", (), {"pid": 321})()),
    )

    msg = streamlit_dashboard.run_streamlit()

    assert launched
    assert launched[0][:3] == [sys.executable, "-m", "streamlit"]
    assert "запущен" in msg


def test_streamlit_run_returns_install_hint_when_missing(monkeypatch):
    monkeypatch.delitem(sys.modules, "streamlit", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "streamlit":
            raise ImportError("streamlit missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    msg = streamlit_dashboard.run_streamlit()
    assert "не установлен" in msg
