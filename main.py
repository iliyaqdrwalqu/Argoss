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
  [FIX-7] Исправлен импорт db_init → src.db_init (ModuleNotFoundError на Windows)
  [FIX-8] KIVY_NO_ARGS=1 — Kivy больше не перехватывает --dashboard, --no-gui и др.
"""

import os
import sys
import signal
import threading

# [FIX-8] Отключаем перехват аргументов командной строки Kivy.
# Без этого Kivy ловит --dashboard, --no-gui и т.д. и падает с ошибкой
# "option --dashboard not recognized". Должно быть ДО любого импорта Kivy.
os.environ.setdefault("KIVY_NO_ARGS", "1")

# [FIX-9] Подавляем окно Kivy при не-mobile запуске
if "--mobile" not in sys.argv:
    os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")
    os.environ.setdefault("KIVY_HEADLESS", "1")

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
from src.db_init import init_db as _init_db          # [FIX-7] правильный путь

log = get_logger("argos.main")


# [FIX-7] Обёртка-совместимость: заменяет ArgosDB() → вызов init_db()
class ArgosDB:
    """Совместимая обёртка над src.db_init.init_db."""
    def __init__(self):
        _init_db()


class ArgosOrchestrator:

    def __init__(self):
        log.info("━" * 48)
        log.info(" ARGOS UNIVERSAL OS v1.4.0 — BOOT")
        log.info("━" * 48)

        self._stop_event = threading.Event()

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

        # 5. Admin + Flasher
        try:
            self.admin = ArgosAdmin()
            self.flasher = AirFlasher()
            log.info("[ADMIN] Файловый менеджер и flasher готовы")
        except Exception as e:
            log.warning("[ADMIN] Ошибка инициализации admin/flasher: %s", e)
            self.admin = None
            self.flasher = None

        # 6. Ядро
        try:
            self.core = ArgosCore()
            log.info("[CORE] ArgosCore готов")
        except Exception as e:
            log.error("[CORE] Критическая ошибка ядра: %s", e)
            raise

        # 7. Telegram
        self.tg = None  # [FIX-4]

    # --- [FIX-4] _start_telegram сохраняет ссылку на поток ---
    def _start_telegram(self):
        try:
            tg = ArgosTelegram(self.core, self.admin, self.flasher)
            t = threading.Thread(target=tg.run, daemon=True, name="ArgosTelegram")
            t.start()
            self.tg = t
            log.info("[TG] Telegram бот запущен")
        except Exception as e:
            log.warning("[TG] Telegram недоступен: %s", e)
            self.tg = None

    def shutdown(self):
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
        # [FIX-GUI-KIVY] Ленивый импорт — Kivy не инициализируется при запуске customtkinter
        try:
            from src.interface.gui import ArgosGUI
        except ImportError:
            from src.interface.kivy_gui import ArgosGUI
            log.warning("customtkinter не найден — Kivy GUI")

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
                self._stop_event.wait(timeout=1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()


# ══════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ══════════════════════════════════════════════════════════════
def main():
    sys.argv = normalize_launch_args(sys.argv)

    # --- [FIX-6] оборачиваем создание оркестратора ---
    try:
        orch = ArgosOrchestrator()
    except Exception as e:
        print(f"[FATAL] Не удалось запустить ARGOS: {e}")
        sys.exit(1)

    # Dashboard (фоновый поток)
    if "--dashboard" in sys.argv:
        try:
            from src.interface.web_engine import ArgosWebEngine
            dash = ArgosWebEngine(orch.core)
            threading.Thread(target=dash.run, daemon=True, name="ArgosDashboard").start()
            log.info("[DASH] Веб-панель запущена: http://localhost:8080")
        except Exception as e:
            log.warning("[DASH] Dashboard недоступен: %s", e)

    # --- [FIX-5] режимы через if/elif ---
    try:
        if "--root" in sys.argv:
            if orch.root:
                print(orch.root.request_root())
            else:
                print("RootManager недоступен.")

        elif "--shell" in sys.argv:
            orch.boot_shell()

        elif "--mobile" in sys.argv:
            orch.boot_mobile()

        elif "--no-gui" in sys.argv:
            orch.boot_server()

        else:
            orch.boot_desktop()

    except Exception as e:
        log.error("[BOOT] Ошибка запуска: %s", e)
        orch.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()