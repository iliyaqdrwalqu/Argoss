import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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

from src.connectivity.telegram_bot import ArgosTelegram, HISTORY_MESSAGES_LIMIT


def _make_bot(user_id: str = "42"):
    core = SimpleNamespace(db=Mock())
    admin = SimpleNamespace()
    flasher = SimpleNamespace()
    bot = ArgosTelegram(core=core, admin=admin, flasher=flasher)
    bot.user_id = user_id
    return bot, core


def test_auth_rejects_non_owner_user():
    bot, _ = _make_bot(user_id="42")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=99))

    assert bot._auth(update) is False


def test_auth_accepts_first_of_multiple_ids():
    """USER_ID=42,99 — пользователь 42 должен проходить."""
    bot, _ = _make_bot(user_id="42,99")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42))
    assert bot._auth(update) is True


def test_auth_accepts_second_of_multiple_ids():
    """USER_ID=42,99 — пользователь 99 должен проходить."""
    bot, _ = _make_bot(user_id="42,99")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=99))
    assert bot._auth(update) is True


def test_auth_rejects_unlisted_user_with_multiple_ids():
    """USER_ID=42,99 — пользователь 100 должен быть заблокирован."""
    bot, _ = _make_bot(user_id="42,99")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=100))
    assert bot._auth(update) is False


def test_auth_rejects_when_user_id_empty():
    """USER_ID='' — никто не должен проходить."""
    bot, _ = _make_bot(user_id="")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42))
    assert bot._auth(update) is False


def test_auth_handles_spaces_in_user_id():
    """USER_ID='42 , 99' — пробелы вокруг ID должны игнорироваться."""
    bot, _ = _make_bot(user_id="42 , 99")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=99))
    assert bot._auth(update) is True


def test_cmd_history_uses_fixed_recent_limit():
    async def _run():
        bot, core = _make_bot(user_id="42")
        core.db.format_history.return_value = "h1\nh2"

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=42),
            message=message,
        )

        await bot.cmd_history(update, None)

        core.db.format_history.assert_called_once_with(HISTORY_MESSAGES_LIMIT)
        message.reply_text.assert_awaited_once_with("h1\nh2")

    asyncio.run(_run())


def test_cmd_start_returns_control_keyboard_markup():
    async def _run():
        bot, _ = _make_bot(user_id="42")
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=42),
            message=message,
        )

        await bot.cmd_start(update, None)

        message.reply_text.assert_awaited_once()
        kwargs = message.reply_text.await_args.kwargs
        markup = kwargs.get("reply_markup")
        assert markup is not None
        buttons = [btn.text for row in markup.keyboard for btn in row]
        assert "/status" in buttons
        assert "/history" in buttons
        assert "/skills" in buttons
        assert "/crypto" in buttons
        assert "/alerts" in buttons
        assert "/apk" in buttons
        assert "/voice_on" in buttons
        assert "/voice_off" in buttons
        assert "/help" in buttons

    asyncio.run(_run())
