"""
root_manager.py — Управление привилегиями суперпользователя
  Windows: UAC-запрос на повышение прав
  Linux:   sudo / pkexec
  Android: su через Magisk/SuperSU
"""
import os
import platform
import subprocess
import sys

class RootManager:
    def __init__(self):
        self.os_type   = platform.system()
        self.is_root   = self._check_root()
        self.is_android = "ANDROID_ROOT" in os.environ

    def _check_root(self) -> bool:
        """Проверяет, запущен ли процесс с правами суперпользователя."""
        if self.os_type == "Windows":
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            except Exception:
                return False
        else:
            return os.geteuid() == 0

    def status(self) -> str:
        if self.is_android:
            rooted = self._check_android_root()
            return (f"📱 Android\n"
                    f"  Root доступен: {'✅ ДА' if rooted else '❌ НЕТ'}\n"
                    f"  {'Используй Magisk для root-доступа.' if not rooted else 'su команды доступны.'}")
        if self.is_root:
            return f"✅ Права суперпользователя активны ({self.os_type})"
        return f"⚠️ Обычные права пользователя ({self.os_type}). Некоторые функции недоступны."

    def _check_android_root(self) -> bool:
        """Проверяет наличие su на Android."""
        su_paths = ["/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su"]
        for path in su_paths:
            if os.path.exists(path):
                return True
        try:
            result = subprocess.run(["which", "su"], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return False

    def request_elevation(self) -> str:
        """Запрашивает повышение привилегий."""
        if self.is_root:
            return "✅ Уже работаю с правами суперпользователя."

        if self.os_type == "Windows":
            return self._elevate_windows()
        elif self.is_android:
            return self._elevate_android()
        else:
            return self._elevate_linux()

    def _elevate_windows(self) -> str:
        """UAC-запрос на Windows."""
        try:
            import ctypes
            script = os.path.abspath(sys.argv[0])
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}"', None, 1
            )
            if result > 32:
                return "✅ Запрос администратора отправлен. Подтверди в UAC-диалоге."
            return "❌ UAC запрос отклонён или уже запущен с правами."
        except Exception as e:
            return f"❌ Ошибка повышения прав Windows: {e}"

    def _elevate_linux(self) -> str:
        """sudo/pkexec на Linux."""
        script = os.path.abspath(sys.argv[0])
        # Пробуем pkexec (графический sudo)
        try:
            result = subprocess.run(
                ["pkexec", sys.executable, script] + sys.argv[1:],
                timeout=5
            )
            return "✅ Запуск через pkexec инициирован."
        except FileNotFoundError:
            pass
        # Fallback: sudo в терминале
        try:
            os.execvp("sudo", ["sudo", sys.executable, script] + sys.argv[1:])
        except Exception as e:
            return f"❌ Не удалось повысить права: {e}"
        return "Перезапуск с sudo..."

    def _elevate_android(self) -> str:
        """su на Android (требует root)."""
        if not self._check_android_root():
            return (
                "❌ ROOT не обнаружен на этом устройстве.\n"
                "Для получения root:\n"
                "  1. Разблокируй загрузчик (bootloader)\n"
                "  2. Установи Magisk через TWRP\n"
                "  3. Перезапусти Аргоса\n"
                "⚠️ Это аннулирует гарантию устройства."
            )
        try:
            result = subprocess.run(
                ["su", "-c", "id"],
                capture_output=True, text=True, timeout=5
            )
            if "uid=0" in result.stdout:
                return "✅ ROOT доступ подтверждён. Аргос работает как суперпользователь."
            return "⚠️ su найден, но uid=0 не получен."
        except Exception as e:
            return f"❌ Ошибка su: {e}"

    def run_as_root(self, command: str) -> str:
        """Выполняет команду с правами суперпользователя."""
        if self.is_android:
            try:
                result = subprocess.run(
                    ["su", "-c", command],
                    capture_output=True, text=True, timeout=15
                )
                return result.stdout or result.stderr or "Команда выполнена."
            except Exception as e:
                return f"❌ su ошибка: {e}"

        if self.os_type != "Windows" and not self.is_root:
            command = f"sudo {command}"

        try:
            result = subprocess.check_output(
                command, shell=True, stderr=subprocess.STDOUT,
                text=True, timeout=30
            )
            return result[:1000]
        except subprocess.CalledProcessError as e:
            return f"❌ Ошибка: {e.output[:500]}"
