"""
kivy_ma.py — ARGOS v1.4.0 Sovereign Node Launcher (Android/Mobile).

[FIX-KIVY-DESKTOP] Kivy импортируется ЛЕНИВО — только внутри launch()
когда реально нужен мобильный режим. Это предотвращает открытие
окна Kivy при десктопном запуске.
"""
from __future__ import annotations

import os
import sys
import threading

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ
IS_COLAB   = "COLAB_GPU" in os.environ or "COLAB_RELEASE_TAG" in os.environ


class SovereignNode:
    def __init__(self, core=None):
        self.core = core
        self.ver  = "1.4.0"
        self.mode = "mobile" if IS_ANDROID else "cloud"

    def process_all(self, cmd: str) -> str:
        if self.core and hasattr(self.core, "process"):
            r = self.core.process(cmd)
            return r.get("answer", str(r)) if isinstance(r, dict) else str(r)
        return f"Exec: {cmd}"

    def launch(self):
        # 1. Веб (cloud/headless)
        if self.mode == "cloud":
            try:
                from src.interface.web_engine import run_web_sync
                threading.Thread(
                    target=run_web_sync,
                    kwargs={"core": self.core},
                    daemon=True,
                ).start()
                print("🌐 [AETHER]: Веб-дашборд запущен на порту 8080")
            except Exception as e:
                print(f"⚠️  Web engine: {e}")

        # 2. Kivy — ТОЛЬКО для Android/mobile, импорт внутри блока
        if self.mode == "mobile":
            try:
                # [FIX] Ленивый импорт — Kivy не трогается при cloud режиме
                from src.interface.kivy_gui import ArgosGUI
                gui = ArgosGUI(core=self.core)
                gui.core_callback = self.process_all
                gui.run()
            except ImportError:
                print("🔱 [TERMINAL]: Kivy недоступен. Используй --no-gui.")
            except Exception as e:
                print(f"🔱 [TERMINAL]: Kivy error: {e}")
        else:
            print("🔱 [TERMINAL MODE]: Веб-интерфейс активен. Telegram бот активен.")


SovereignNodeMA = SovereignNode


def launch(core=None):
    SovereignNode(core=core).launch()


if __name__ == "__main__":
    launch()
