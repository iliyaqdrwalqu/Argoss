"""
android_service.py — ArgosOmniService unified background service для Android.
Работает через Kivy/Plyer Service API или как Termux background job.
"""
import os
import time
import threading
from src.argos_logger import get_logger

log = get_logger("argos.android_service")

IS_ANDROID = os.path.exists("/system/build.prop")


class ArgosOmniService:
    """Фоновый сервис Аргоса для Android/Termux."""

    def __init__(self, core=None):
        self.core = core
        self._running = False
        self._tasks: list = []
        self._thread: threading.Thread = None

    def start(self) -> str:
        if self._running:
            return "ℹ️ OmniService уже запущен"
        self._running = True
        self._thread = threading.Thread(target=self._service_loop, daemon=True)
        self._thread.start()
        if IS_ANDROID:
            self._request_android_wakelock()
        log.info("ArgosOmniService запущен (Android=%s)", IS_ANDROID)
        return "✅ ArgosOmniService запущен"

    def stop(self) -> str:
        self._running = False
        return "✅ ArgosOmniService остановлен"

    def _service_loop(self):
        while self._running:
            try:
                # Heartbeat + выполнение фоновых задач
                for task in list(self._tasks):
                    try:
                        task()
                    except Exception as e:
                        log.debug("OmniService task: %s", e)
                self._background_checks()
            except Exception as e:
                log.debug("OmniService loop: %s", e)
            time.sleep(10)

    def _background_checks(self):
        """Периодические фоновые проверки."""
        if self.core:
            try:
                # Проверяем Telegram-сообщения
                if hasattr(self.core, "telegram") and self.core.telegram:
                    pass  # Telegram polling уже в своём потоке
                # Проверяем алерты
                if hasattr(self.core, "alert_system") and self.core.alert_system:
                    self.core.alert_system.check()
            except Exception:
                pass

    def _request_android_wakelock(self):
        """Запрашивает WakeLock на Android через pyjnius."""
        try:
            from jnius import autoclass
            PythonService = autoclass("org.kivy.android.PythonService")
            PythonService.mService.setAutoRestartService(True)
            log.info("Android WakeLock: OK")
        except Exception:
            # Termux fallback
            try:
                os.system("termux-wake-lock")
                log.info("Termux wake-lock: OK")
            except Exception:
                pass

    def register_task(self, fn) -> None:
        """Регистрирует фоновую задачу."""
        self._tasks.append(fn)

    def send_android_notification(self, title: str, text: str) -> str:
        """Отправляет уведомление Android."""
        if not IS_ANDROID:
            return f"[NOTIFY] {title}: {text}"
        try:
            from plyer import notification
            notification.notify(title=title, message=text, app_name="Argos")
            return f"✅ Уведомление отправлено: {title}"
        except Exception:
            try:
                os.system(f'termux-notification --title "{title}" --content "{text}"')
                return f"✅ Termux notification: {title}"
            except Exception as e:
                return f"❌ Notification: {e}"

    def status(self) -> str:
        return (
            f"📱 ARGOS OMNI SERVICE:\n"
            f"  Android:  {'✅' if IS_ANDROID else '❌ (desktop)'}\n"
            f"  Запущен:  {'✅' if self._running else '❌'}\n"
            f"  Задач:    {len(self._tasks)}"
        )

# Alias
AndroidService = ArgosOmniService
