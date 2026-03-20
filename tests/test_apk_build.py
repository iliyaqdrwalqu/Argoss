"""Tests for ArgosTelegram._build_apk_sync() behaviour."""
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock, patch

if "telegram" not in sys.modules:
    telegram_mod = types.ModuleType("telegram")
    telegram_mod.Update = object

    class KeyboardButton:
        def __init__(self, text):
            self.text = text

    class ReplyKeyboardMarkup:
        def __init__(self, keyboard, **kwargs):
            self.keyboard = keyboard
            self.kwargs = kwargs

    telegram_mod.KeyboardButton = KeyboardButton
    telegram_mod.ReplyKeyboardMarkup = ReplyKeyboardMarkup
    sys.modules["telegram"] = telegram_mod

    telegram_error_mod = types.ModuleType("telegram.error")

    class InvalidToken(Exception):
        pass

    class TelegramError(Exception):
        pass

    telegram_error_mod.InvalidToken = InvalidToken
    telegram_error_mod.TelegramError = TelegramError
    sys.modules["telegram.error"] = telegram_error_mod

    telegram_ext_mod = types.ModuleType("telegram.ext")
    telegram_ext_mod.Application = object
    telegram_ext_mod.MessageHandler = object
    telegram_ext_mod.CommandHandler = object
    telegram_ext_mod.filters = SimpleNamespace(
        VOICE=object(), AUDIO=object(), PHOTO=object(), TEXT=object(), COMMAND=object()
    )
    telegram_ext_mod.ContextTypes = SimpleNamespace(DEFAULT_TYPE=object)
    sys.modules["telegram.ext"] = telegram_ext_mod

from src.connectivity.telegram_bot import ArgosTelegram


def _make_bot():
    core = SimpleNamespace(db=Mock())
    admin = SimpleNamespace()
    flasher = SimpleNamespace()
    return ArgosTelegram(core=core, admin=admin, flasher=flasher)


# ── ARGOS_APK_BUILD_CMD empty / unset ────────────────────────────────────────

def test_build_apk_returns_error_when_cmd_empty(monkeypatch):
    monkeypatch.delenv("ARGOS_APK_BUILD_CMD", raising=False)
    bot = _make_bot()
    ok, msg = bot._build_apk_sync()
    assert not ok
    assert "ARGOS_APK_BUILD_CMD" in msg


def test_build_apk_returns_error_when_cmd_whitespace_only(monkeypatch):
    monkeypatch.setenv("ARGOS_APK_BUILD_CMD", "   ")
    bot = _make_bot()
    ok, msg = bot._build_apk_sync()
    assert not ok
    assert "ARGOS_APK_BUILD_CMD" in msg


# ── Successful build (mocked subprocess + artifact) ──────────────────────────

def test_build_apk_calls_subprocess_with_split_command(monkeypatch, tmp_path):
    """subprocess.run must receive a list (not a string), confirming shlex.split usage."""
    monkeypatch.setenv("ARGOS_APK_BUILD_CMD", "buildozer -v android debug")
    bot = _make_bot()

    captured_args = []

    def fake_run(args, **kwargs):
        captured_args.append(args)

    monkeypatch.setattr("subprocess.run", fake_run)

    # Fake an APK artifact so the method reports success
    apk_file = tmp_path / "app.apk"
    apk_file.write_text("fake")
    monkeypatch.setattr(bot, "_find_apk_artifact", lambda: str(apk_file))

    ok, result = bot._build_apk_sync()

    assert len(captured_args) == 1
    assert isinstance(captured_args[0], list), "subprocess.run должен получать список, а не строку"
    assert captured_args[0] == ["buildozer", "-v", "android", "debug"]
    assert ok
    assert str(apk_file) in result


# ── Failed build (CalledProcessError) ────────────────────────────────────────

def test_build_apk_returns_error_on_called_process_error(monkeypatch):
    import subprocess
    monkeypatch.setenv("ARGOS_APK_BUILD_CMD", "buildozer android debug")
    bot = _make_bot()

    def fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr("subprocess.run", fake_run)

    ok, msg = bot._build_apk_sync()
    assert not ok
    assert "ошибкой" in msg.lower()


# ── APK not found after build ─────────────────────────────────────────────────

def test_build_apk_returns_error_when_artifact_missing(monkeypatch):
    monkeypatch.setenv("ARGOS_APK_BUILD_CMD", "buildozer android debug")
    bot = _make_bot()

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: None)
    monkeypatch.setattr(bot, "_find_apk_artifact", lambda: None)

    ok, msg = bot._build_apk_sync()
    assert not ok
    assert "не найден" in msg.lower() or "APK" in msg
