# ======================================================
# ARGOS v1.33 — Android / Kivy entry point
# ======================================================
# This is the entry point used by buildozer for the APK.
# It intentionally imports only Kivy-compatible modules
# and avoids desktop-only libraries (aiogram, streamlit, etc.).
# ======================================================

from src.interface.kivy_1gui import ArgosGUI


if __name__ == "__main__":
    ArgosGUI().run()
