"""
streamlit_dashboard.py — Streamlit-админка поверх FastAPI.
Запуск: streamlit run src/interface/streamlit_dashboard.py
"""

import os
import subprocess
import sys

API = os.getenv("ARGOS_DASHBOARD_API", "http://localhost:8080").rstrip("/")

try:
    import requests
    import streamlit as st

    st.set_page_config(page_title="Argos Streamlit Dashboard", layout="wide")
    st.title("👁️ Argos Streamlit Dashboard")
    st.caption(f"API: {API}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Метрики")
        try:
            status = requests.get(f"{API}/api/status", timeout=5).json()
            st.metric("CPU", f"{status.get('cpu', 0):.1f}%")
            st.metric("RAM", f"{status.get('ram', 0):.1f}%")
            st.metric("Disk", f"{status.get('disk', 0):.1f}%")
        except Exception as e:
            st.error(f"Не удалось получить статус: {e}")

    with col2:
        st.subheader("Команда")
        cmd = st.text_input("Введите директиву")
        if st.button("Выполнить") and cmd.strip():
            try:
                resp = requests.post(
                    f"{API}/api/cmd", json={"cmd": cmd}, timeout=20).json()
                st.code(resp.get("answer", str(resp)))
            except Exception as e:
                st.error(f"Ошибка: {e}")

    st.subheader("Логи")
    try:
        logs = requests.get(f"{API}/api/log", timeout=5).json().get("lines", "")
        st.text_area("Последние строки", logs, height=300)
    except Exception as e:
        st.error(f"Не удалось получить логи: {e}")

except ImportError:
    pass


def run_streamlit():
    """Точка входа (для импорта). Запускает streamlit-процесс."""
    try:
        import streamlit  # noqa: F401
    except ImportError:
        return "❌ Streamlit не установлен. Установи: pip install streamlit"
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", __file__])
    return f"✅ Streamlit dashboard запущен (pid={proc.pid}): streamlit run {__file__}"


StreamlitDashboard = type("StreamlitDashboard", (), {"run": staticmethod(run_streamlit)})
