# ======================================================
# ARGOS v1.4.0 — Android / Kivy entry point
# ======================================================
# This is the entry point used by buildozer for the APK.
# It intentionally imports only Kivy-compatible modules
# and avoids desktop-only libraries (aiogram, streamlit, etc.).
#
# Remote Control client — connects to ARGOS server via HTTP API.
# Set Server URL and ARGOS_REMOTE_TOKEN in the Settings tab.
# ======================================================

from src.interface.kivy_remote_ui import ArgosRemoteApp


if __name__ == "__main__":
    ArgosRemoteApp().run()
