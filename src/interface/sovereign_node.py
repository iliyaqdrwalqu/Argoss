\
"""
sovereign_node.py — SovereignNode: универсальный узел Аргоса
  Автоопределение режима: mobile (Kivy) / cloud (Web) / headless
"""
import os
import sys
import threading
from src.argos_logger import get_logger
log = get_logger("argos.sovereign")

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ
IS_COLAB   = "COLAB_GPU" in os.environ or "COLAB_RELEASE_TAG" in os.environ


class SovereignNode:
    """Автоопределение режима и запуск нужного интерфейса."""

    def __init__(self, core=None):
        self.core = core
        self.ver  = "1.33.0"
        if IS_ANDROID:
            self.mode = "mobile"
        elif IS_COLAB:
            self.mode = "cloud"
        else:
            self.mode = os.getenv("ARGOS_MODE", "cloud")

    def launch(self):
        log.info("SovereignNode v%s | mode=%s", self.ver, self.mode)

        # 1. Web-интерфейс в фоне (cloud/colab)
        if self.mode in ("cloud", "headless"):
            self._start_web()
            self._print_info()
            return

        # 2. Kivy GUI (mobile/desktop)
        if self.mode == "mobile":
            self._start_web()          # web тоже стартует в фоне
            self._start_kivy()
            return

        # 3. Headless
        self._print_info()

    def _start_web(self):
        from src.interface.web_engine import WebDashboard
        wd = WebDashboard(core=self.core)
        t = threading.Thread(target=wd.run, daemon=True, name="WebDashboard")
        t.start()
        port = int(os.getenv("ARGOS_DASHBOARD_PORT", "8080"))
        log.info("🌐 Aether Interface → http://0.0.0.0:%d", port)

    def _start_kivy(self):
        try:
            from src.interface.kivy_gui import ArgosGUI
            gui = ArgosGUI(core=self.core)
            log.info("📱 Запуск Kivy GUI...")
            gui.run()
        except ImportError:
            log.warning("Kivy недоступен — переключение в headless")
            self._print_info()
        except Exception as e:
            log.error("Kivy GUI error: %s", e)
            self._print_info()

    def _print_info(self):
        port = int(os.getenv("ARGOS_DASHBOARD_PORT", "8080"))
        print("─" * 52)
        print("  🔱 ARGOS SOVEREIGN NODE v1.3")
        print(f"  Mode: {self.mode}")
        print(f"  Web:  http://0.0.0.0:{port}")
        print("  Telegram: активен (если настроен)")
        print("─" * 52)

    def process_all(self, cmd: str) -> str:
        """Прямой вызов ядра — для Kivy callback."""
        if self.core:
            r = self.core.process(cmd)
            return r.get("answer", str(r)) if isinstance(r, dict) else str(r)
        return f"[Core недоступен] {cmd}"
