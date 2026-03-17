"""
main.py — ArgosUniversal OS v1.4.0
  Оркестратор: запускает все подсистемы в правильном порядке.
  Режимы: desktop | mobile | server
  Флаги:  --no-gui | --mobile | --root | --dashboard | --wake
"""
import os, sys, threading
from dotenv import load_dotenv
load_dotenv()

from src.core                        import ArgosCore
from src.admin                       import ArgosAdmin
from src.security.git_guard          import GitGuard
from src.security.encryption         import ArgosShield
from src.security.root_manager       import RootManager
from src.factory.flasher             import AirFlasher
from src.connectivity.spatial        import SpatialAwareness
from src.connectivity.telegram_bot   import ArgosTelegram
from src.argos_logger                import get_logger
from src.launch_config               import normalize_launch_args
from db_init                         import ArgosDB

log = get_logger("argos.main")


class ArgosOrchestrator:
    def __init__(self):
        log.info("━" * 48)
        log.info("  ARGOS UNIVERSAL OS v1.4.0 — BOOT")
        log.info("━" * 48)

        # 1. Безопасность
        GitGuard().check_security()
        self.shield = ArgosShield()
        log.info("[SHIELD] AES-256 активирован")

        # 2. Права
        self.root = RootManager()
        log.info("[ROOT] %s", self.root.status().split('\n')[0])

        # 3. База данных
        self.db = ArgosDB()
        log.info("[DB] SQLite ready → data/argos.db")

        # 4. Геолокация
        self.spatial  = SpatialAwareness(db=self.db)
        self.location = self.spatial.get_location()
        log.info("[GEO] %s", self.location)

        # 5. Инструменты
        self.admin   = ArgosAdmin()
        self.flasher = AirFlasher()

        # 6. Ядро
        self.core    = ArgosCore()
        self.core.db = self.db

        # 7. P2P
        p2p = self.core.start_p2p()
        log.info("[P2P] %s", p2p.split('\n')[0])

        # 8. Веб-панель
        if "--dashboard" in sys.argv:
            dash = self.core.start_dashboard(self.admin, self.flasher)
            log.info("[DASH] %s", dash)

        log.info("━" * 48)
        log.info("  АРГОС ПРОБУЖДЁН. ЖДУ ДИРЕКТИВ.")
        log.info("━" * 48)

    def _start_telegram(self):
        try:
            self.tg = ArgosTelegram(self.core, self.admin, self.flasher)
            can_start, reason = self.tg.can_start()
            if not can_start:
                log.warning("[TG] Отключён: %s", reason)
                return
            threading.Thread(target=self.tg.run, daemon=True).start()
            log.info("[TG] Telegram-бот запущен")
        except Exception as e:
            log.warning("[TG] Не запущен: %s", e)

    def boot_desktop(self):
        from src.interface.gui import ArgosGUI
        self._start_telegram()
        app = ArgosGUI(self.core, self.admin, self.flasher, self.location)
        app._append(
            f"👁️  ARGOS UNIVERSAL OS v1.4.0\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Создатель: Всеволод\n"
            f"Гео:       {self.location}\n"
            f"Права:     {'ROOT ✅' if self.root.is_root else 'User ⚠️'}\n"
            f"ИИ:        {self.core.ai_mode_label()}\n"
            f"Память:    {'✅' if self.core.memory else '❌'}\n"
            f"Vision:    {'✅' if self.core.vision else '❌'}\n"
            f"Алерты:    {'✅' if self.core.alerts else '❌'}\n"
            f"P2P:       {'✅' if self.core.p2p else '❌'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Напечатай 'помощь' для списка команд.\n\n",
            "#00FF88"
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
        # Для шелла не обязательно запускать Telegram сразу, но можно.
        # self._start_telegram() 
        from src.interface.argos_shell import ArgosShell
        try:
            ArgosShell().cmdloop()
        except KeyboardInterrupt:
            print("\nShell terminated.")

    def boot_server(self):
        log.info("[SERVER] Headless режим — только Telegram + P2P")
        if "--dashboard" in sys.argv:
            log.info("[SERVER] Dashboard: http://localhost:8080")
        self._start_telegram()
        import time
        try:
            while True: time.sleep(60)
        except KeyboardInterrupt:
            log.info("Аргос завершает работу.")


if __name__ == "__main__":
    sys.argv = [sys.argv[0], *normalize_launch_args(sys.argv[1:])]

    for d in ["logs","config","builds/replicas","assets","data"]:
        os.makedirs(d, exist_ok=True)

    if "--root" in sys.argv:
        print(RootManager().request_elevation()); sys.exit(0)

    mode = "desktop"
    if "--no-gui"  in sys.argv: mode = "server"
    if "--mobile"  in sys.argv: mode = "mobile"
    if "--shell"   in sys.argv: mode = "shell"

    argos = ArgosOrchestrator()
    if   mode == "desktop": argos.boot_desktop()
    elif mode == "mobile":  argos.boot_mobile()
    elif mode == "shell":   argos.boot_shell()
    else:                   argos.boot_server()
