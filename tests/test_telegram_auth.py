"""Tests for ArgosTelegram._auth() — single and multiple USER_ID support."""
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


def _make_bot(user_id: str = "42"):
    core = SimpleNamespace(db=Mock())
    admin = SimpleNamespace()
    flasher = SimpleNamespace()
    bot = ArgosTelegram(core=core, admin=admin, flasher=flasher)
    bot.user_id = user_id
    bot.allowed_ids = {uid.strip() for uid in user_id.split(",") if uid.strip()}
    return bot


def _update(uid: int):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid))


# ── Single USER_ID ────────────────────────────────────────────────────────────

def test_auth_accepts_single_user():
    bot = _make_bot("42")
    assert bot._auth(_update(42)) is True


def test_auth_rejects_unknown_user_single():
    bot = _make_bot("42")
    assert bot._auth(_update(99)) is False


# ── Multiple USER_ID via comma ────────────────────────────────────────────────

def test_auth_accepts_first_of_multiple():
    bot = _make_bot("42,99,123")
    assert bot._auth(_update(42)) is True


def test_auth_accepts_middle_of_multiple():
    bot = _make_bot("42,99,123")
    assert bot._auth(_update(99)) is True


def test_auth_accepts_last_of_multiple():
    bot = _make_bot("42,99,123")
    assert bot._auth(_update(123)) is True


def test_auth_rejects_unlisted_user_multiple():
    bot = _make_bot("42,99,123")
    assert bot._auth(_update(1000)) is False


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_auth_rejects_when_user_id_empty():
    bot = _make_bot("")
    assert bot._auth(_update(42)) is False


def test_auth_rejects_when_only_commas():
    bot = _make_bot(",,,")
    assert bot._auth(_update(42)) is False


def test_auth_handles_spaces_around_ids():
    bot = _make_bot("42 , 99 , 123")
    assert bot._auth(_update(99)) is True


def test_auth_allowed_ids_populated_in_init(monkeypatch):
    """allowed_ids must be populated from USER_ID env var at construction time."""
    monkeypatch.setenv("USER_ID", "55,66")
    core = SimpleNamespace(db=Mock())
    bot = ArgosTelegram(core=core, admin=SimpleNamespace(), flasher=SimpleNamespace())
    assert "55" in bot.allowed_ids
    assert "66" in bot.allowed_ids
    assert len(bot.allowed_ids) == 2
