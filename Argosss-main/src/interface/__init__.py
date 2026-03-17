\
# ARGOS Interface modules
from src.interface.web_engine import WebDashboard, run_web_sync
try:
    from src.interface.kivy_gui import ArgosGUI
except ImportError:
    pass
