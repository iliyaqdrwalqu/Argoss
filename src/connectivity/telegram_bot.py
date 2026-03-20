import os
import asyncio
import tempfile
import subprocess
from pathlib import Path
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.error import InvalidToken, TelegramError
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    filters, ContextTypes
)

HISTORY_MESSAGES_LIMIT = 10


class ArgosTelegram:
    def __init__(self, core, admin, flasher):
        self.core    = core
        self.admin   = admin
        self.flasher = flasher
        self.token   = os.getenv("TELEGRAM_BOT_TOKEN")
        self.user_id = os.getenv("USER_ID")
        self.app     = None

    def _find_apk_artifact(self) -> str | None:
        candidates = []
        for pattern in ["bin/*.apk", "dist/**/*.apk", "build/**/*.apk"]:
            candidates.extend(Path(".").glob(pattern))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(candidates[0])

    def _build_apk_sync(self) -> tuple[bool, str]:
        """Собирает APK внешней командой из ARGOS_APK_BUILD_CMD."""
        cmd = os.getenv("ARGOS_APK_BUILD_CMD", "").strip()
        if not cmd:
            return False, "ARGOS_APK_BUILD_CMD не задан. Пример: buildozer -v android debug"

        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            return False, f"Сборка APK завершилась с ошибкой: {e}"
        except Exception as e:
            return False, f"Ошибка запуска сборки APK: {e}"

        apk_path = self._find_apk_artifact()
        if not apk_path:
            return False, "Сборка завершена, но APK не найден (bin/dist/build)."
        return True, apk_path

    def _is_placeholder_token(self, token: str) -> bool:
        value = (token or "").strip().lower()
        return value in {"", "your_token_here", "none", "null", "changeme"}

    def _looks_like_token(self, token: str) -> bool:
        t = (token or "").strip()
        if ":" not in t:
            return False
        bot_id, secret = t.split(":", 1)
        return bot_id.isdigit() and len(secret) >= 30

    def can_start(self) -> tuple[bool, str]:
        if self._is_placeholder_token(self.token):
            return False, "Токен не задан"
        if not self._looks_like_token(self.token):
            return False, "Формат токена некорректен"
        if not self.user_id:
            return False, "USER_ID не задан"
        return True, "ok"

    # ── ПРОВЕРКА ДОСТУПА ──────────────────────────────────
    def _auth(self, update: Update) -> bool:
        """Проверяет доступ. USER_ID может содержать несколько ID через запятую: 123,456,789."""
        user_id = str(update.effective_user.id)
        allowed_ids = {uid.strip() for uid in (self.user_id or "").split(",") if uid.strip()}
        if not allowed_ids:
            return False
        return user_id in allowed_ids

    # ── КОМАНДЫ ───────────────────────────────────────────
    def _control_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("/status"), KeyboardButton("/history"), KeyboardButton("/help")],
                [KeyboardButton("/voice_on"), KeyboardButton("/voice_off"), KeyboardButton("/skills")],
                [KeyboardButton("/crypto"), KeyboardButton("/alerts"), KeyboardButton("/apk")],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Выбери команду или отправь директиву...",
        )

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        await update.message.reply_text(
            "👁️ *АРГОС ОНЛАЙН*\n\n"
            "Доступные команды:\n"
            "/status — здоровье системы\n"
            "/crypto — BTC/ETH курсы\n"
            "/history — история диалога\n"
            "/geo — геолокация\n"
            "/memory — долгосрочная память\n"
            "/alerts — статус алертов\n"
            "/network — P2P сеть\n"
            "/sync — синхронизация навыков\n"
            "/replicate — создать копию\n"
            "/smart — умные системы\n"
            "/iot — IoT устройства\n"
            "`iot протоколы` — список поддерживаемых протоколов\n"
            "`статус устройства [id]` — мониторинг устройства\n"
            "`создай прошивку [id] [шаблон] [порт]` — подготовка/прошивка\n"
            "`изучи протокол [шаблон] [протокол] [прошивка] [описание]` — выучить новый протокол\n"
            "`изучи устройство [шаблон] [протокол] [hardware]` — выучить новое устройство\n"
            "/skills — список навыков\n"
            "/voice_on /voice_off — озвучка\n"
            "/apk — собрать и отправить APK\n"
            "/help — справка\n\n"
            "Или отправь директиву текстом/голосом/фото/аудио.",
            parse_mode="Markdown",
            reply_markup=self._control_keyboard(),
        )

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        stats  = self.admin.get_stats()
        health = self.core.sensors.get_full_report()
        state  = self.core.quantum.generate_state()
        msg = (
            f"📊 *СИСТЕМНЫЙ ДОКЛАД*\n\n"
            f"{stats}\n\n"
            f"{health}\n\n"
            f"⚛️ Квантовое состояние: `{{state['name']}}`\n"
            f"Вектор: `{{state['vector']}}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_voice_on(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        self.core.voice_on = True
        await update.message.reply_text("🔊 Голосовой модуль активирован.")

    async def cmd_voice_off(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        self.core.voice_on = False
        await update.message.reply_text("🔇 Голосовой модуль отключён.")

    async def cmd_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        from src.evolution import ArgosEvolution
        report = ArgosEvolution().list_skills()
        await update.message.reply_text(report)

    async def cmd_network(self, update, ctx):
        if not self._auth(update): return
        if self.core.p2p:
            await update.message.reply_text(self.core.p2p.network_status())
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_sync(self, update, ctx):
        if not self._auth(update): return
        await update.message.reply_text("🔄 Синхронизирую навыки со всеми нодами...")
        if self.core.p2p:
            result = self.core.p2p.sync_skills_from_network()
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_crypto(self, update, ctx):
        if not self._auth(update): return
        try:
            from src.skills.crypto_monitor import CryptoSentinel
            report = CryptoSentinel().report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Крипто: {{e}}")

    async def cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        if self.core.db:
            hist = self.core.db.format_history(HISTORY_MESSAGES_LIMIT)
            await update.message.reply_text(hist[:4000])
        else:
            await update.message.reply_text("БД не подключена.")

    async def cmd_geo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        try:
            from src.connectivity.spatial import SpatialAwareness
            report = SpatialAwareness(db=self.core.db).get_full_report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Геолокация: {{e}}")

    async def cmd_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        if self.core.memory:
            await update.message.reply_text(self.core.memory.format_memory()[:4000])
        else:
            await update.message.reply_text("Память не активирована.")

    async def cmd_alerts(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        if self.core.alerts:
            await update.message.reply_text(self.core.alerts.status())
        else:
            await update.message.reply_text("Система алертов не активирована.")

    async def cmd_replicate(self, update, ctx):
        if not self._auth(update): return
        await update.message.reply_text("📦 Создаю реплику системы...")
        try:
            result = self.core.replicator.create_replica()
            await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text(f"❌ {{e}}")

    async def cmd_smart(self, update, ctx):
        """Статус умных систем."""
        if not self._auth(update): return
        if self.core.smart_sys:
            report = self.core.smart_sys.full_status()
            await update.message.reply_text(report[:4000])
        else:
            await update.message.reply_text("Умные системы не подключены.")

    async def cmd_iot(self, update, ctx):
        """Статус IoT устройств."""
        if not self._auth(update): return
        if self.core.iot_bridge:
            await update.message.reply_text(self.core.iot_bridge.status()[:4000])
        else:
            await update.message.reply_text("IoT Bridge не подключен.")

    async def cmd_apk(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Собрать APK и отправить файл в Telegram."""
        if not self._auth(update):
            return
        await update.message.reply_text("📦 Запускаю сборку APK. Это может занять несколько минут...")
        ok, payload = await asyncio.to_thread(self._build_apk_sync)
        if not ok:
            await update.message.reply_text(f"❌ {{payload}}")
            return

        apk_path = payload
        try:
            with open(apk_path, "rb") as f:
                await update.message.reply_document(document=f, filename=os.path.basename(apk_path), caption="✅ APK готов")
        except Exception as e:
            await update.message.reply_text(f"❌ Не удалось отправить APK: {{e}}")

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return
        help_text = (
            "👁️ *АРГОС — СПРАВОЧНИК*\n\n"
            "*Администрирование:*\n"
            "• `статус системы` — мониторинг ЦП/ОЗУ/диска\n"
            "• `покажи файлы [путь]` — содержимое папки\n"
            "• `прочитай файл [путь]` — чтение файла\n"
            "• `создай файл [имя] [текст]` — создать файл\n"
            "• `удали файл [путь]` — удалить файл\n"
            "• `консоль [команда]` — выполнить в терминале\n"
            "• `убей процесс [имя]` — завершить процесс\n\n"
            "*Навыки:*\n"
            "• `крипто` — цены BTC/ETH\n"
            "• `дайджест` — AI новости\n"
            "• `сканируй сеть` — устройства в сети\n"
            "• `сканируй порты` — открытые порты\n"
            "• `репликация` — создать архив системы\n\n"
            "*IoT / Mesh / Прошивка:*\n"
            "• `iot статус` — сводка всех устройств\n"
            "• `статус устройства [id]` — детальный мониторинг устройства\n"
            "• `iot протоколы` — BACnet, Modbus, KNX, LonWorks, M-Bus, OPC UA, MQTT\n"
            "• `подключи zigbee [host] [port]` / `подключи lora [port] [baud]`\n"
            "• `запусти mesh` / `статус mesh`\n"
            "• `изучи протокол [шаблон] [протокол] [прошивка] [описание]`\n"
            "• `изучи устройство [шаблон] [протокол] [hardware]`\n"
            "• `создай прошивку [id] [шаблон] [порт]` — создать/обновить прошивку\n"
            "• `шаблоны шлюзов` — доступные профили gateway\n\n"
            "*Голос:*\n"
            "• `/voice_on` / `/voice_off` — TTS\n"
            "• Отправь голосовое сообщение — Аргос распознает и выполнит команду\n"
            "• Отправь аудиофайл — Аргос расшифрует и выполнит команду\n"
            "\n*Изображения / Камера:*\n"
            "• Отправь фото — Аргос проанализирует изображение через Vision AI\n"
            "• Фото с подписью — подпись используется как вопрос к изображению\n"
            "\n*APK:*\n"
            "• `/apk` — сборка APK и отправка в Telegram (через ARGOS_APK_BUILD_CMD)\n"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    # ── ОСНОВНОЙ ОБРАБОТЧИК ───────────────────────────────
    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            await update.message.reply_text(
                "⛔ Доступ заблокирован. Попытка входа зафиксирована."
            )
            return

        user_text = update.message.text
        await update.message.reply_text("⚙️ Обрабатываю директиву...")

        result = await self.core.process_logic_async(user_text, self.admin, self.flasher)
        answer = result['answer'][:4000]  # Telegram лимит
        state  = result['state']

        await update.message.reply_text(
            f"👁️ *ARGOS* `[{state}]`\n\n{{answer}}",
            parse_mode="Markdown"
        )

    async def handle_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            await update.message.reply_text("⛔ Доступ заблокирован.")
            return

        voice = update.message.voice if update.message else None
        if not voice:
            await update.message.reply_text("❌ Голосовое сообщение не обнаружено.")
            return

        await update.message.reply_text("🎙 Получил голосовое. Распознаю...")

        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(voice.file_id)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                temp_path = tmp.name

            await tg_file.download_to_drive(custom_path=temp_path)
            text = await asyncio.to_thread(self.core.transcribe_audio_path, temp_path)

            if not text:
                await update.message.reply_text("🤷 Не удалось распознать голосовое. Попробуйте ещё раз.")
                return

            await update.message.reply_text(f"📝 Распознано: {{text}}")
            result = await self.core.process_logic_async(text, self.admin, self.flasher)
            answer = result['answer'][:4000]
            state = result['state']
            await update.message.reply_text(
                f"👁️ *ARGOS* `[{state}]`\n\n{{answer}}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка обработки голосового: {{e}}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    async def handle_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Принимает фото/изображение и анализирует через Vision AI."""
        if not self._auth(update):
            await update.message.reply_text("⛔ Доступ заблокирован.")
            return

        photo = update.message.photo[-1] if update.message.photo else None
        if not photo:
            await update.message.reply_text("❌ Изображение не обнаружено.")
            return

        caption = update.message.caption or "Опиши что на изображении подробно."
        await update.message.reply_text("🖼 Получил изображение. Анализирую...")

        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_path = tmp.name

            await tg_file.download_to_drive(custom_path=temp_path)

            if self.core.vision:
                result = await asyncio.to_thread(
                    self.core.vision.analyze_image, temp_path, caption
                )
            else:
                result = "❌ Vision модуль не инициализирован. Установи: pip install google-genai Pillow"

            await update.message.reply_text(result[:4000])
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка анализа изображения: {{e}}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    async def handle_audio(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Принимает аудиофайл (не голосовую заметку) и транскрибирует через Whisper."""
        if not self._auth(update):
            await update.message.reply_text("⛔ Доступ заблокирован.")
            return

        audio = update.message.audio if update.message else None
        if not audio:
            await update.message.reply_text("❌ Аудиофайл не обнаружен.")
            return

        await update.message.reply_text("🎵 Получил аудиофайл. Расшифровываю...")

        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(audio.file_id)
            suffix = os.path.splitext(audio.file_name)[1] if audio.file_name else ".mp3"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                temp_path = tmp.name

            await tg_file.download_to_drive(custom_path=temp_path)
            text = await asyncio.to_thread(self.core.transcribe_audio_path, temp_path)

            if not text:
                await update.message.reply_text("🤷 Не удалось расшифровать аудио. Попробуйте ещё раз.")
                return

            await update.message.reply_text(f"📝 Распознано: {{text}}")
            result = await self.core.process_logic_async(text, self.admin, self.flasher)
            answer = result['answer'][:4000]
            state = result['state']
            await update.message.reply_text(
                f"👁️ *ARGOS* `[{state}]`\n\n{{answer}}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка обработки аудио: {{e}}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    # ── ЗАПУСК ────────────────────────────────────────────
    def run(self):
        can_start, reason = self.can_start()
        if not can_start:
            print(f"[TG-BRIDGE]: Telegram-мост отключён: {{reason}}.")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self.app = Application.builder().token(self.token).build()

        # Delete any existing webhook to prevent conflicts
        loop.run_until_complete(self.app.bot.delete_webhook(drop_pending_updates=True))

        # Команды
        self.app.add_handler(CommandHandler("start",     self.cmd_start))
        self.app.add_handler(CommandHandler("status",    self.cmd_status))
        self.app.add_handler(CommandHandler("voice_on",  self.cmd_voice_on))
        self.app.add_handler(CommandHandler("voice_off", self.cmd_voice_off))
        self.app.add_handler(CommandHandler("skills",    self.cmd_skills))
        self.app.add_handler(CommandHandler("help",      self.cmd_help))
        self.app.add_handler(CommandHandler("network",   self.cmd_network))
        self.app.add_handler(CommandHandler("sync",      self.cmd_sync))
        self.app.add_handler(CommandHandler("crypto",    self.cmd_crypto))
        self.app.add_handler(CommandHandler("history",   self.cmd_history))
        self.app.add_handler(CommandHandler("geo",       self.cmd_geo))
        self.app.add_handler(CommandHandler("memory",    self.cmd_memory))
        self.app.add_handler(CommandHandler("alerts",    self.cmd_alerts))
        self.app.add_handler(CommandHandler("replicate", self.cmd_replicate))
        self.app.add_handler(CommandHandler("smart",     self.cmd_smart))
        self.app.add_handler(CommandHandler("iot",       self.cmd_iot))
        self.app.add_handler(CommandHandler("apk",       self.cmd_apk))

        # Текстовые сообщения
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        try:
            loop.run_until_complete(self.app.bot.get_me())
        except InvalidToken:
            print("[TG-BRIDGE]: Telegram-мост отключён: токен отклонён сервером.")
            return
        except TelegramError as e:
            print(f"[TG-BRIDGE]: Telegram preflight error: {{e}}")
            return
        except Exception as e:
            print(f"[TG-BRIDGE]: Telegram preflight unexpected error: {{e}}")
            return

        _allowed = ", ".join(uid.strip() for uid in (self.user_id or "").split(",") if uid.strip())
        print(f"[TG-BRIDGE]: Мост активен. Разрешённые USER_ID: [{_allowed}]")
        try:
            self.app.run_polling(close_loop=False, drop_pending_updates=True)
        except InvalidToken:
            print("[TG-BRIDGE]: Telegram-мост отключён: токен отклонён сервером.")
        except TelegramError as e:
            print(f"[TG-BRIDGE]: Telegram error: {{e}}")
        except Exception as e:
            print(f"[TG-BRIDGE]: Неожиданная ошибка Telegram-моста: {{e}}")