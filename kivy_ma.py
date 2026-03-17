import os, sys, threading, requests

# --- УНИВЕРСАЛЬНАЯ ИНИЦИАЛИЗАЦИЯ ---
try:
    from src.interface.kivy_gui import ArgosGUI
    GUI_AVAIL = True
except:
    GUI_AVAIL = False

class SovereignNode:
    def __init__(self):
        self.ver = "1.33.0"
        self.mode = "mobile" if 'ANDROID_ARGUMENT' in os.environ else "cloud"

    def process_all(self, cmd):
        # Тут твоя логика shell, root, bt, nfc
        return "Exec: " + cmd

# Функция для запуска в фоновых потоках
def launch():
    node = SovereignNode()
    
    # 1. Запуск Web-интерфейса (Для ПК и Colab)
    if node.mode == "cloud":
        from src.interface.web_engine import run_web_sync
        threading.Thread(target=run_web_sync, daemon=True).start()

    # 2. Запуск GUI (Для телефона)
    if GUI_AVAIL and node.mode == "mobile":
        gui = ArgosGUI()
        gui.core_callback = node.process_all
        gui.run()
    else:
        print("🔱 [TERMINAL MODE]: Веб-интерфейс на порту 8080. Бот Telegram Активен.")

if __name__ == "__main__":
    launch()