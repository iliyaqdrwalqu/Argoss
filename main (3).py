"""
main.py — ArgosUniversal OS v1.4.0
Оркестратор: запускает все подсистемы в правильном порядке.
Режимы: desktop | mobile | server
Флаги: --no-gui | --mobile | --root | --dashboard | --wake

ПАТЧИ (исправленные баги):
  [FIX-1] RootManager импортируется в начале файла (был NameError при --root)
  [FIX-2] Каждый шаг __init__ изолирован в try/except (частичный сбой не роняет всё)
  [FIX-3] boot_server использует threading.Event + signal.SIGTERM (graceful shutdown)
  [FIX-4] _start_telegram сохраняет ссылку на поток, tg=None при сбое
  [FIX-5] Режимы запуска разбираются через if/elif (нет конфликта флагов)
  [FIX-6] ArgosOrchestrator() и boot_*() обёрнуты в try/except с понятными сообщениями
"""

import os
import sys
import signal
import threading

from dotenv import load_dotenv
load_dotenv()

from src.core import ArgosCore
from src.admin import ArgosAdmin
from src.security.git_guard import GitGuard
from src.security.encryption import ArgosShield
from src.security.root_manager import RootManager   # [FIX-1] перенесён наверх
from src.factory.flasher import AirFlasher
from src.connectivity.spatial import SpatialAwareness
from src.connectivity.telegram_bot import ArgosTelegram
from src.argos_logger import get_logger
from src.launch_config import normalize_launch_args
from db_init import ArgosDB

log = get_logger("argos.main")


class ArgosOrchestrator:

    def __init__(self):
        log.info("━" * 48)
        log.info(" ARGOS UNIVERSAL OS v1.4.0 — BOOT")
        log.info("━" * 48)

        # --- [FIX-2] каждый некритичный шаг изолирован ---

        # 1. Безопасность
        try:
            GitGuard().check_security()
            self.shield = ArgosShield()
            log.info("[SHIELD] AES-256 активирован")
        except Exception as e:
            log.warning("[SHIELD] Инициализация защиты с ошибкой: %s", e)
            self.shield = None

        # 2. Права
        try:
            self.root = RootManager()
            log.info("[ROOT] %s", self.root.status().split('\n')[0])
        except Exception as e:
            log.warning("[ROOT] RootManager недоступен: %s", e)
            self.root = None

        # 3. База данных
        try:
            self.db = ArgosDB()
            log.info("[DB] SQLite ready → data/argos.db")
        except Exception as e:
            log.error("[DB] Ошибка инициализации БД: %s — работаю без персистентности", e)
            self.db = None

        # 4. Геолокация
        try:
            self.spatial = SpatialAwareness(db=self.db)
            self.location = self.spatial.get_location()
            log.info("[GEO] %s", self.location)
        except Exception as e:
            log.warning("[GEO] Геолокация недоступна: %s", e)
            self.location = "неизвестно"

        # 5. Инструменты
        try:
            self.admin = ArgosAdmin()
            self.flasher = AirFlasher()
        except Exception as e:
            log.warning("[TOOLS] Инструменты недоступны: %s", e)
            self.admin = None
            self.flasher = None

        # 6. Ядро — критично, без него нельзя работать
        try:
            self.core = ArgosCore()
            if self.db:
                self.core.db = self.db
        except Exception as e:
            log.critical("[CORE] Не удалось запустить ядро: %s", e)
            raise  # пробрасываем — без ядра нет смысла продолжать

        # 7. P2P
        try:
            p2p = self.core.start_p2p()
            log.info("[P2P] %s", p2p.split('\n')[0])
        except Exception as e:
            log.warning("[P2P] P2P недоступен: %s", e)

        # 8. Веб-панель
        if "--dashboard" in sys.argv:
            try:
                dash = self.core.start_dashboard(self.admin, self.flasher)
                log.info("[DASH] %s", dash)
            except Exception as e:
                log.warning("[DASH] Dashboard не запущен: %s", e)

        # служебные атрибуты для graceful shutdown
        self.tg = None
        self._tg_thread = None
        self._stop_event = threading.Event()

        log.info("━" * 48)
        log.info(" АРГОС ПРОБУЖДЁН. ЖДУ ДИРЕКТИВ.")
        log.info("━" * 48)

    # --- [FIX-4] сохраняем ссылку на поток, tg=None при сбое ---
    def _start_telegram(self):
        try:
            self.tg = ArgosTelegram(self.core, self.admin, self.flasher)
            can_start, reason = self.tg.can_start()
            if not can_start:
                log.warning("[TG] Отключён: %s", reason)
                self.tg = None
                return
            self._tg_thread = threading.Thread(
                target=self.tg.run,
                daemon=True,
                name="argos-telegram",
            )
            self._tg_thread.start()
            log.info("[TG] Telegram-бот запущен")
        except Exception as e:
            log.warning("[TG] Не запущен: %s", e)
            self.tg = None

    def _shutdown(self):
        """Корректное завершение всех подсистем."""
        log.info("Аргос завершает работу...")
        try:
            if self.core:
                if hasattr(self.core, 'p2p') and self.core.p2p:
                    self.core.p2p.stop()
                if hasattr(self.core, 'alerts') and self.core.alerts:
                    self.core.alerts.stop()
        except Exception as e:
            log.warning("Ошибка при shutdown: %s", e)

    def boot_desktop(self):
        from src.interface.gui import ArgosGUI
        self._start_telegram()

        is_root = self.root.is_root if self.root else False
        app = ArgosGUI(self.core, self.admin, self.flasher, self.location)
        app._append(
            f"👁️ ARGOS UNIVERSAL OS v1.4.0\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Создатель: Всеволод\n"
            f"Гео: {self.location}\n"
            f"Права: {'ROOT ✅' if is_root else 'User ⚠️'}\n"
            f"ИИ: {self.core.ai_mode_label()}\n"
            f"Память: {'✅' if self.core.memory else '❌'}\n"
            f"Vision: {'✅' if self.core.vision else '❌'}\n"
            f"Алерты: {'✅' if self.core.alerts else '❌'}\n"
            f"P2P: {'✅' if self.core.p2p else '❌'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Напечатай 'помощь' для списка команд.\n\n",
            "#00FF88",
        )
        if "--wake" in sys.argv:
            ww = self.core.start_wake_word(self.admin, self.flasher)
            app._append(f"{ww}\n", "#00ffff")
        app.mainloop()

    def boot_mobile(self):
        from src.interface.mobile_ui import ArgosMobileUI
        ArgosMobileUI(core=self.core, admin=self.admin, flasher=self.flasher).run()

    def boot_shell(self):
        """Интерактивная оболочка Argos (замена bash/cmd)."""
        log.info("[SHELL] Low-level REPL mode activated.")
        print("\n--- [ Argos System Shell ] ---\n")
        from src.interface.argos_shell import ArgosShell
        try:
            ArgosShell().cmdloop()
        except KeyboardInterrupt:
            print("\nShell terminated.")

    # --- [FIX-3] graceful shutdown через threading.Event + SIGTERM ---
    def boot_server(self):
        log.info("[SERVER] Headless режим — только Telegram + P2P")
        if "--dashboard" in sys.argv:
            log.info("[SERVER] Dashboard: http://localhost:8080")

        self._start_telegram()

        def _handle_signal(signum, frame):
            log.info("Получен сигнал %s — завершаю работу...", signum)
            self._stop_event.set()

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT,  _handle_signal)

        log.info("[SERVER] Жду директив. Для остановки: CTRL+C или SIGTERM.")
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=5)
        finally:
            self._shutdown()


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.argv = [sys.argv[0], *normalize_launch_args(sys.argv[1:])]

    for d in ["logs", "config", "builds/replicas", "assets", "data"]:
        os.makedirs(d, exist_ok=True)

    # [FIX-1] RootManager теперь импортирован вверху — NameError невозможен
    if "--root" in sys.argv:
        print(RootManager().request_elevation())
        sys.exit(0)

    # [FIX-5] if/elif — нет конфликта флагов; приоритет: shell > mobile > server > desktop
    args = set(sys.argv[1:])
    conflict = args & {"--no-gui", "--mobile", "--shell"}
    if len(conflict) > 1:
        log.warning("Конфликт режимов запуска: %s. Используется приоритетный.", conflict)

    mode = "desktop"
    if   "--shell"  in args: mode = "shell"
    elif "--mobile" in args: mode = "mobile"
    elif "--no-gui" in args: mode = "server"

    # [FIX-6] обёртка с понятными сообщениями об ошибках
    try:
        argos = ArgosOrchestrator()
    except Exception as e:
        print(f"\n❌ ARGOS: Критическая ошибка при инициализации:\n  {e}")
        print("Запусти 'python health_check.py' для диагностики.")
        sys.exit(1)

    boot_map = {
        "desktop": argos.boot_desktop,
        "mobile":  argos.boot_mobile,
        "shell":   argos.boot_shell,
        "server":  argos.boot_server,
    }

    try:
        boot_map.get(mode, argos.boot_server)()
    except KeyboardInterrupt:
        log.info("Аргос завершает работу по команде пользователя.")
    except Exception as e:
        log.critical("Фатальная ошибка в режиме '%s': %s", mode, e, exc_info=True)
        sys.exit(1)
