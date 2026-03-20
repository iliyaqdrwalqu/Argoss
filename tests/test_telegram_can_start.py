"""Tests for ArgosTelegram.can_start() with various token and USER_ID configurations."""
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

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


def _make_bot(token: str = "", user_id: str = "42"):
    core = SimpleNamespace(db=Mock())
    admin = SimpleNamespace()
    flasher = SimpleNamespace()
    bot = ArgosTelegram(core=core, admin=admin, flasher=flasher)
    bot.token = token
    bot.user_id = user_id
    bot.allowed_ids = {uid.strip() for uid in user_id.split(",") if uid.strip()}
    return bot


# ── Placeholder / empty token tests ──────────────────────────────────────────

def test_can_start_fails_when_token_empty():
    bot = _make_bot(token="", user_id="42")
    ok, reason = bot.can_start()
    assert not ok
    assert "Токен" in reason


def test_can_start_fails_with_placeholder_your_token_here():
    bot = _make_bot(token="your_token_here", user_id="42")
    ok, reason = bot.can_start()
    assert not ok
    assert "Токен" in reason


def test_can_start_fails_with_placeholder_none():
    bot = _make_bot(token="none", user_id="42")
    ok, reason = bot.can_start()
    assert not ok


def test_can_start_fails_with_placeholder_changeme():
    bot = _make_bot(token="changeme", user_id="42")
    ok, reason = bot.can_start()
    assert not ok


def test_can_start_fails_when_token_format_wrong_no_colon():
    bot = _make_bot(token="notavalidtoken", user_id="42")
    ok, reason = bot.can_start()
    assert not ok
    assert "формат" in reason.lower()


def test_can_start_fails_when_token_secret_too_short():
    bot = _make_bot(token="123456:short", user_id="42")
    ok, reason = bot.can_start()
    assert not ok


def test_can_start_fails_when_user_id_empty():
    bot = _make_bot(token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", user_id="")
    ok, reason = bot.can_start()
    assert not ok
    assert "USER_ID" in reason


def test_can_start_succeeds_with_valid_token_and_user_id():
    bot = _make_bot(token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", user_id="42")
    ok, reason = bot.can_start()
    assert ok
    assert reason == "ok"


def test_can_start_succeeds_with_multiple_user_ids():
    bot = _make_bot(token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", user_id="42,99,100")
    ok, reason = bot.can_start()
    assert ok
