import asyncio
import logging
import aiosqlite
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
from openai import AsyncOpenAI
import os

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    logging.critical(
        "TELEGRAM_TOKEN не задан! "
        "Скопируйте .env.example в .env и укажите токен бота от @BotFather."
    )
    sys.exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()
openai_client = AsyncOpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

log = logging.getLogger(__name__)

# Telegram hard limit for message text length
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
# Number of most-recent messages passed to the AI as context
GPT_CONTEXT_LIMIT = 80
# Hard cap for persisted messages per chat to avoid unbounded history retention
MAX_STORED_MESSAGES_PER_CHAT = 500
# ISO datetime format "YYYY-MM-DD HH:MM:SS" is 19 characters
DATETIME_DISPLAY_LENGTH = 19

# ====================== SQLite ======================
DB_NAME = "chat_history.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                text TEXT,
                date TEXT
            )
        ''')
        await db.commit()

async def save_message(chat_id: int, user_id: int, username: str, full_name: str, text: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO messages (chat_id, user_id, username, full_name, text, date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (chat_id, user_id, username, full_name, text, datetime.now().isoformat()))
        await db.execute('''
            DELETE FROM messages
            WHERE chat_id = ?
              AND id NOT IN (
                SELECT id FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
              )
        ''', (chat_id, chat_id, MAX_STORED_MESSAGES_PER_CHAT))
        await db.commit()

async def get_recent_history(chat_id: int, limit: int = 100) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        # Fetch the most recent rows in reverse, then re-order ascending for readability
        async with db.execute('''
            SELECT full_name, text, date FROM (
                SELECT id, full_name, text, date FROM messages
                WHERE chat_id = ? ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC
        ''', (chat_id, limit)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return "История пуста."
    return "\n".join([f"[{date[:DATETIME_DISPLAY_LENGTH]}] {name}: {text}" for name, text, date in rows])

# ====================== AI with bounded recent context ======================
async def get_gpt_response(chat_id: int, user_message: str) -> str:
    if not openai_client:
        return (
            "⚠️ OPENAI_API_KEY не задан в .env\n"
            "Бот работает без GPT. Установите ключ и перезапустите."
        )

    history_text = await get_recent_history(chat_id, limit=GPT_CONTEXT_LIMIT)

    system_prompt = (
        "Ты умный дружелюбный помощник системы ARGOS v1.33. "
        "У тебя есть только недавний контекст чата ниже. "
        "Отвечай максимально полезно, с юмором и учитывая контекст.\n\n"
        f"=== ПОСЛЕДНИЕ {GPT_CONTEXT_LIMIT} СООБЩЕНИЙ ЧАТА ===\n{history_text}\n=== КОНЕЦ КОНТЕКСТА ===\n\n"
        f"Пользователь сейчас написал: {user_message}\n"
        "Отвечай только на русском, коротко и по делу."
    )

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка OpenAI: {e}"

# ====================== Handlers ======================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🔱 *ARGOS v1.33 ONLINE*\n\n"
        "Команды:\n"
        "/history — последние 50 сообщений\n"
        "/clear — очистить историю\n"
        "/argos \\<команда\\> — выполнить команду ARGOS\n\n"
        "Команды ARGOS: nfc, bt, wifi, root, gps, status, build apk, "
        "build firmware, model status, model update, 7z pack \\<путь\\>, help",
        parse_mode="MarkdownV2",
    )

@dp.message(Command("history"))
async def cmd_history(message: Message):
    hist = await get_recent_history(message.chat.id, limit=50)
    preview = hist[:TELEGRAM_MAX_MESSAGE_LENGTH]
    await message.answer("📜 Последние 50 сообщений:\n\n" + preview)

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM messages WHERE chat_id = ?", (message.chat.id,))
        await db.commit()
    await message.answer("✅ Вся история этого чата удалена из базы.")

@dp.message(Command("argos"))
async def cmd_argos(message: Message):
    """Выполнить команду ARGOS напрямую через Telegram."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ Использование: /argos <команда>\n"
            "Пример: /argos status\n"
            "Пример: /argos build firmware\n"
            "Команда help покажет все доступные команды."
        )
        return
    cmd = parts[1].strip()
    try:
        # Импортируем ArgosAbsolute из main.py
        import importlib.util, sys as _sys
        import os as _os
        _spec = importlib.util.spec_from_file_location(
            "argos_main",
            _os.path.join(_os.path.dirname(__file__), "main.py"),
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        core = _mod.ArgosAbsolute()
        result = core.execute(cmd)
    except Exception as e:
        result = f"❌ Ошибка выполнения: {e}"
    # Разбить длинный ответ на части (все части, без ограничения)
    for i in range(0, len(result), TELEGRAM_MAX_MESSAGE_LENGTH):
        await message.answer(result[i:i + TELEGRAM_MAX_MESSAGE_LENGTH])

@dp.message()
async def all_messages(message: Message):
    text = message.text or f"[НЕ ТЕКСТ: {message.content_type}]"
    await save_message(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        username=message.from_user.username or "no_username",
        full_name=message.from_user.full_name,
        text=text,
    )

    # In group chats, skip non-text messages
    if message.chat.type in ["group", "supergroup"] and not message.text:
        return

    thinking = await message.answer("🤔 Думаю...")
    gpt_text = await get_gpt_response(message.chat.id, text)
    await thinking.edit_text(gpt_text)

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot started. Saving bounded recent history to SQLite and replying via ChatGPT.")
    log.info("For group chats: BotFather → /setprivacy → Disable, then re-add bot to the group.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
