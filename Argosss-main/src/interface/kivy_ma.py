"""
kivy_ma.py — ARGOS v1.33 Sovereign Node Launcher
Альтернативный минимальный лаунчер для мобильного/облачного режима.
Оригинал: kivy_ma.py (main branch). Интегрирован в src/interface/.
"""
import os
import sys
import threading

try:
    from src.interface.kivy_gui import ArgosGUI
    GUI_AVAIL = True
except Exception:
    GUI_AVAIL = False

# Определение режима
IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ
IS_COLAB   = "COLAB_GPU" in os.environ or "COLAB_RELEASE_TAG" in os.environ


class SovereignNode:
    """
    Минимальный SovereignNode — лаунчер мобильного/облачного режима.
    Используется как entry-point для kivy_ma.py интерфейса.
    """

    def __init__(self, core=None):
        self.core = core
        self.ver  = "1.33.0"
        self.mode = "mobile" if IS_ANDROID else "cloud"

    def process_all(self, cmd: str) -> str:
        """Маршрутизация команды в ядро."""
        if self.core and hasattr(self.core, "process"):
            r = self.core.process(cmd)
            return r.get("answer", str(r)) if isinstance(r, dict) else str(r)
        return f"Exec: {cmd}"

    def launch(self):
        """Запустить соответствующий интерфейс."""
        # 1. Веб-интерфейс (PC / Colab / headless)
        if self.mode == "cloud":
            try:
                from src.interface.web_engine import run_web_sync
                t = threading.Thread(target=run_web_sync, kwargs={"core": self.core}, daemon=True)
                t.start()
                print("🌐 [AETHER]: Веб-дашборд запущен на порту 8080")
            except Exception as e:
                print(f"⚠️  Web engine error: {e}")

        # 2. Kivy GUI (мобильный режим)
        if GUI_AVAIL and self.mode == "mobile":
            try:
                gui = ArgosGUI(core=self.core)
                gui.core_callback = self.process_all
                gui.run()
            except Exception:
                print("🔱 [TERMINAL MODE]: Kivy недоступен. Используй --no-gui режим.")
        else:
            print("🔱 [TERMINAL MODE]: Веб-интерфейс на порту 8080. Бот Telegram активен.")


SovereignNodeMA = SovereignNode


def launch(core=None):
    """Entry-point для запуска через import."""
    node = SovereignNode(core=core)
    node.launch()


if __name__ == "__main__":
    launch()
