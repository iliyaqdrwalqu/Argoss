# ARGOS Interface modules
# [FIX-KIVY-DESKTOP] Kivy импортируется ТОЛЬКО при --mobile флаге.
# Не импортируем kivy_gui здесь — это вызывает окно Kivy на десктопе.
 
from src.interface.web_engine import WebDashboard, run_web_sync
 
# ArgosGUI (customtkinter) — только для десктопа
try:
    from src.interface.gui import ArgosGUI
except ImportError:
    ArgosGUI = None  # type: ignore
 
__all__ = ["WebDashboard", "run_web_sync", "ArgosGUI"]
 