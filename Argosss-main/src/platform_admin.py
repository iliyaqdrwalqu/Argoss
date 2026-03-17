"""
platform_admin.py — Кроссплатформенное администрирование Аргоса

Поддерживаемые платформы:
  • Linux   — apt/dpkg/snap/flatpak, systemctl, journalctl, ufw, ip, useradd…
  • Windows — winget, sc/Get-Service, registry, Event Log, Windows Defender…
  • Android — adb/pm/am, Termux pkg, battery, storage, settings…

Graceful degradation: при недоступных инструментах возвращает понятное сообщение.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import textwrap
from typing import List, Optional

from src.argos_logger import get_logger

log = get_logger("argos.platform_admin")

# ── Определение платформы ─────────────────────────────────────────────────────
_OS       = platform.system()          # "Linux" | "Windows" | "Darwin"
_IS_ANDROID = os.path.exists("/system/build.prop") or "ANDROID_ROOT" in os.environ
_IS_TERMUX  = "com.termux" in os.environ.get("PREFIX", "")


def _run(cmd: List[str], timeout: int = 15, input_text: str | None = None) -> str:
    """Выполняет команду и возвращает объединённый stdout+stderr (≤ 3000 символов)."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:3000] if out else "(нет вывода)"
    except FileNotFoundError:
        return f"❌ Команда не найдена: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"⏱ Таймаут {timeout}с"
    except Exception as e:
        return f"❌ {e}"


def _cmd_available(name: str) -> bool:
    return shutil.which(name) is not None


# ══════════════════════════════════════════════════════════════════════════════
# LINUX
# ══════════════════════════════════════════════════════════════════════════════

class LinuxAdmin:
    """Администрирование Linux-систем."""

    # ── Пакетный менеджер ─────────────────────────────────────────────────────
    def pkg_install(self, name: str) -> str:
        if _cmd_available("apt-get"):
            return _run(["sudo", "apt-get", "install", "-y", name], timeout=120)
        if _cmd_available("dnf"):
            return _run(["sudo", "dnf", "install", "-y", name], timeout=120)
        if _cmd_available("pacman"):
            return _run(["sudo", "pacman", "-S", "--noconfirm", name], timeout=120)
        return "❌ Поддерживаемый пакетный менеджер не найден (apt/dnf/pacman)"

    def pkg_remove(self, name: str) -> str:
        if _cmd_available("apt-get"):
            return _run(["sudo", "apt-get", "remove", "-y", name])
        if _cmd_available("dnf"):
            return _run(["sudo", "dnf", "remove", "-y", name])
        if _cmd_available("pacman"):
            return _run(["sudo", "pacman", "-R", "--noconfirm", name])
        return "❌ Пакетный менеджер не найден"

    def pkg_update(self) -> str:
        if _cmd_available("apt-get"):
            r1 = _run(["sudo", "apt-get", "update"], timeout=60)
            r2 = _run(["sudo", "apt-get", "upgrade", "-y"], timeout=300)
            return f"--- update ---\n{r1}\n--- upgrade ---\n{r2}"
        if _cmd_available("dnf"):
            return _run(["sudo", "dnf", "update", "-y"], timeout=300)
        if _cmd_available("pacman"):
            return _run(["sudo", "pacman", "-Syu", "--noconfirm"], timeout=300)
        return "❌ Пакетный менеджер не найден"

    def pkg_search(self, query: str) -> str:
        if _cmd_available("apt-cache"):
            return _run(["apt-cache", "search", query])
        if _cmd_available("dnf"):
            return _run(["dnf", "search", query])
        if _cmd_available("pacman"):
            return _run(["pacman", "-Ss", query])
        return "❌ Пакетный менеджер не найден"

    def pkg_list_installed(self) -> str:
        if _cmd_available("dpkg"):
            return _run(["dpkg", "--get-selections"])
        if _cmd_available("rpm"):
            return _run(["rpm", "-qa"])
        if _cmd_available("pacman"):
            return _run(["pacman", "-Q"])
        return "❌ Менеджер пакетов не найден"

    def snap_install(self, name: str) -> str:
        return _run(["sudo", "snap", "install", name], timeout=120)

    def snap_list(self) -> str:
        return _run(["snap", "list"])

    # ── Сервисы systemd ───────────────────────────────────────────────────────
    def service_start(self, name: str) -> str:
        return _run(["sudo", "systemctl", "start", name])

    def service_stop(self, name: str) -> str:
        return _run(["sudo", "systemctl", "stop", name])

    def service_restart(self, name: str) -> str:
        return _run(["sudo", "systemctl", "restart", name])

    def service_status(self, name: str) -> str:
        return _run(["systemctl", "status", name, "--no-pager", "-l"])

    def service_enable(self, name: str) -> str:
        return _run(["sudo", "systemctl", "enable", name])

    def service_disable(self, name: str) -> str:
        return _run(["sudo", "systemctl", "disable", name])

    def service_list(self) -> str:
        return _run(["systemctl", "list-units", "--type=service", "--no-pager"])

    # ── Логи ──────────────────────────────────────────────────────────────────
    def logs(self, unit: str = "", lines: int = 50) -> str:
        cmd = ["journalctl", "--no-pager", "-n", str(lines)]
        if unit:
            cmd += ["-u", unit]
        return _run(cmd)

    def dmesg(self, lines: int = 30) -> str:
        return _run(["dmesg", "-T", "--level=err,warn"], timeout=10)

    # ── Диск и хранилище ──────────────────────────────────────────────────────
    def disk_usage(self) -> str:
        return _run(["df", "-h", "--output=source,size,used,avail,pcent,target"])

    def dir_size(self, path: str = ".") -> str:
        return _run(["du", "-sh", path])

    # ── Пользователи ─────────────────────────────────────────────────────────
    def user_info(self) -> str:
        whoami = _run(["whoami"])
        uid    = _run(["id"])
        groups = _run(["groups"])
        return f"👤 Пользователь: {whoami}\n  ID: {uid}\n  Группы: {groups}"

    def user_list(self) -> str:
        return _run(["cut", "-d:", "-f1", "/etc/passwd"])

    def user_add(self, username: str) -> str:
        return _run(["sudo", "useradd", "-m", username])

    def user_del(self, username: str) -> str:
        return _run(["sudo", "userdel", "-r", username])

    def passwd(self, username: str, new_pass: str) -> str:
        return _run(["sudo", "chpasswd"], input_text=f"{username}:{new_pass}\n")

    # ── Сеть ──────────────────────────────────────────────────────────────────
    def network_info(self) -> str:
        ip  = _run(["ip", "addr", "show"])
        rt  = _run(["ip", "route"])
        return f"📡 Интерфейсы:\n{ip}\n\n🛣️ Маршруты:\n{rt}"

    def ss_connections(self) -> str:
        if _cmd_available("ss"):
            return _run(["ss", "-tulnp"])
        return _run(["netstat", "-tulnp"])

    def firewall_status(self) -> str:
        if _cmd_available("ufw"):
            return _run(["sudo", "ufw", "status", "verbose"])
        if _cmd_available("firewall-cmd"):
            return _run(["sudo", "firewall-cmd", "--list-all"])
        return "⚠️ UFW и firewalld не найдены"

    # ── Система ───────────────────────────────────────────────────────────────
    def sys_info(self) -> str:
        uname  = _run(["uname", "-a"])
        lsb    = _run(["lsb_release", "-a"]) if _cmd_available("lsb_release") else ""
        uptime = _run(["uptime"])
        mem    = _run(["free", "-h"])
        lines  = [f"🖥️ {uname}", f"⏰ {uptime}", f"💾 RAM:\n{mem}"]
        if lsb:
            lines.insert(1, lsb)
        return "\n".join(lines)

    def cpu_info(self) -> str:
        return _run(["lscpu"])

    def top_processes(self, count: int = 10) -> str:
        return _run(["ps", "aux", "--sort=-%cpu"])[:2000]


# ══════════════════════════════════════════════════════════════════════════════
# WINDOWS
# ══════════════════════════════════════════════════════════════════════════════

class WindowsAdmin:
    """Администрирование Windows-систем."""

    # ── Пакеты (winget) ───────────────────────────────────────────────────────
    def pkg_install(self, name: str) -> str:
        return _run(["winget", "install", "--silent", "--accept-package-agreements",
                     "--accept-source-agreements", name], timeout=180)

    def pkg_remove(self, name: str) -> str:
        return _run(["winget", "uninstall", "--silent", name], timeout=60)

    def pkg_upgrade(self, name: str = "") -> str:
        cmd = ["winget", "upgrade", "--all", "--silent",
               "--accept-package-agreements", "--accept-source-agreements"]
        if name:
            cmd = ["winget", "upgrade", name, "--silent",
                   "--accept-package-agreements", "--accept-source-agreements"]
        return _run(cmd, timeout=300)

    def pkg_search(self, query: str) -> str:
        return _run(["winget", "search", query])

    def pkg_list(self) -> str:
        return _run(["winget", "list"])

    # ── Сервисы ───────────────────────────────────────────────────────────────
    def service_start(self, name: str) -> str:
        return _run(["sc", "start", name])

    def service_stop(self, name: str) -> str:
        return _run(["sc", "stop", name])

    def service_status(self, name: str) -> str:
        return _run(["sc", "query", name])

    def service_list(self) -> str:
        return _run(["sc", "query", "type=", "all", "state=", "all"])

    def service_enable(self, name: str) -> str:
        return _run(["sc", "config", name, "start=", "auto"])

    def service_disable(self, name: str) -> str:
        return _run(["sc", "config", name, "start=", "disabled"])

    # ── Реестр ────────────────────────────────────────────────────────────────
    def reg_query(self, key: str, value: str = "") -> str:
        cmd = ["reg", "query", key]
        if value:
            cmd += ["/v", value]
        return _run(cmd)

    def reg_set(self, key: str, value: str, data: str, reg_type: str = "REG_SZ") -> str:
        return _run(["reg", "add", key, "/v", value, "/t", reg_type, "/d", data, "/f"])

    def reg_delete(self, key: str, value: str = "") -> str:
        cmd = ["reg", "delete", key, "/f"]
        if value:
            cmd += ["/v", value]
        return _run(cmd)

    # ── Процессы ──────────────────────────────────────────────────────────────
    def task_list(self) -> str:
        return _run(["tasklist", "/v"])

    def task_kill(self, name_or_pid: str) -> str:
        if name_or_pid.isdigit():
            return _run(["taskkill", "/PID", name_or_pid, "/F"])
        return _run(["taskkill", "/IM", name_or_pid, "/F"])

    # ── Сеть ──────────────────────────────────────────────────────────────────
    def network_info(self) -> str:
        return _run(["ipconfig", "/all"])

    def netstat(self) -> str:
        return _run(["netstat", "-ano"])

    def firewall_status(self) -> str:
        return _run(["netsh", "advfirewall", "show", "allprofiles", "state"])

    def firewall_enable(self) -> str:
        return _run(["netsh", "advfirewall", "set", "allprofiles", "state", "on"])

    def firewall_disable(self) -> str:
        return _run(["netsh", "advfirewall", "set", "allprofiles", "state", "off"])

    # ── Обновления Windows ────────────────────────────────────────────────────
    def windows_update(self) -> str:
        return _run(["powershell", "-Command",
                     "Install-Module PSWindowsUpdate -Force -SkipPublisherCheck; "
                     "Get-WindowsUpdate -Install -AcceptAll"], timeout=600)

    def windows_update_check(self) -> str:
        return _run(["powershell", "-Command",
                     "Get-HotFix | Sort-Object InstalledOn -Descending | "
                     "Select-Object -First 20 | Format-Table"])

    # ── Логи событий ──────────────────────────────────────────────────────────
    def event_log(self, log_name: str = "System", count: int = 20,
                  level: str = "Error") -> str:
        return _run(["powershell", "-Command",
                     f"Get-EventLog -LogName {log_name} -Newest {count} "
                     f"-EntryType {level} | Format-List"])

    # ── Disk / System ─────────────────────────────────────────────────────────
    def disk_usage(self) -> str:
        return _run(["powershell", "-Command",
                     "Get-PSDrive -PSProvider FileSystem | "
                     "Format-Table Name,Used,Free,Description"])

    def sys_info(self) -> str:
        return _run(["systeminfo"])

    def defender_status(self) -> str:
        return _run(["powershell", "-Command",
                     "Get-MpComputerStatus | Format-List"])

    def defender_scan(self, path: str = "") -> str:
        target = f'-ScanPath "{path}"' if path else "-ScanType QuickScan"
        return _run(["powershell", "-Command",
                     f"Start-MpScan {target}"], timeout=300)

    # ── Пользователи ─────────────────────────────────────────────────────────
    def user_list(self) -> str:
        return _run(["net", "user"])

    def user_add(self, username: str, password: str = "Argos@12345") -> str:
        return _run(["net", "user", username, password, "/add"])

    def user_del(self, username: str) -> str:
        return _run(["net", "user", username, "/delete"])

    def user_info(self) -> str:
        return _run(["whoami", "/all"])


# ══════════════════════════════════════════════════════════════════════════════
# ANDROID
# ══════════════════════════════════════════════════════════════════════════════

class AndroidAdmin:
    """Администрирование Android-устройств (локально через Termux или удалённо через ADB)."""

    def _adb(self, *args, timeout: int = 30) -> str:
        """Выполняет команду через ADB (если ADB доступен)."""
        if not _cmd_available("adb"):
            return "❌ ADB не найден. Установи Android SDK Platform-Tools."
        return _run(["adb"] + list(args), timeout=timeout)

    def _termux(self, *args, timeout: int = 30) -> str:
        """Выполняет команду через Termux-API или pkg."""
        return _run(list(args), timeout=timeout)

    def _shell(self, cmd: str) -> str:
        """adb shell <cmd>"""
        return self._adb("shell", cmd)

    # ── ADB устройства ───────────────────────────────────────────────────────
    def adb_devices(self) -> str:
        return self._adb("devices", "-l")

    def adb_connect(self, host: str, port: int = 5555) -> str:
        return self._adb("connect", f"{host}:{port}")

    def adb_disconnect(self, host: str = "") -> str:
        if host:
            return self._adb("disconnect", host)
        return self._adb("disconnect")

    # ── Приложения (pm / adb) ────────────────────────────────────────────────
    def app_list(self, filter_flag: str = "") -> str:
        """Список установленных пакетов. filter_flag: -3 (пользовательские), -s (системные)."""
        cmd = "pm list packages"
        if filter_flag:
            cmd += f" {filter_flag}"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def app_install(self, apk_path: str) -> str:
        if _IS_ANDROID:
            return _run(["pm", "install", "-r", apk_path])
        return self._adb("install", "-r", apk_path)

    def app_uninstall(self, package: str, keep_data: bool = False) -> str:
        flags = ["-k"] if keep_data else []
        if _IS_ANDROID:
            return _run(["pm", "uninstall"] + flags + [package])
        return self._adb("uninstall", *(["-k"] if keep_data else []), package)

    def app_info(self, package: str) -> str:
        cmd = f"dumpsys package {package}"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def app_start(self, package: str, activity: str = "") -> str:
        target = f"{package}/{activity}" if activity else package
        cmd = f"am start -n {target}"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def app_stop(self, package: str) -> str:
        cmd = f"am force-stop {package}"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def app_clear(self, package: str) -> str:
        cmd = f"pm clear {package}"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    # ── Termux пакеты ────────────────────────────────────────────────────────
    def termux_install(self, name: str) -> str:
        if not _cmd_available("pkg"):
            return "❌ pkg не найден. Запускается только в Termux."
        return _run(["pkg", "install", "-y", name], timeout=120)

    def termux_remove(self, name: str) -> str:
        if not _cmd_available("pkg"):
            return "❌ pkg не найден"
        return _run(["pkg", "remove", "-y", name])

    def termux_update(self) -> str:
        if not _cmd_available("pkg"):
            return "❌ pkg не найден"
        return _run(["pkg", "update", "-y"], timeout=120)

    def termux_search(self, query: str) -> str:
        if not _cmd_available("pkg"):
            return "❌ pkg не найден"
        return _run(["pkg", "search", query])

    def termux_list(self) -> str:
        if not _cmd_available("pkg"):
            return "❌ pkg не найден"
        return _run(["pkg", "list-installed"])

    # ── Системная информация ──────────────────────────────────────────────────
    def battery_info(self) -> str:
        if _IS_ANDROID and _cmd_available("termux-battery-status"):
            return _run(["termux-battery-status"])
        cmd = "dumpsys battery"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def storage_info(self) -> str:
        if _IS_ANDROID:
            return _run(["df", "-h"])
        return self._shell("df -h")

    def cpu_info(self) -> str:
        cmd = "cat /proc/cpuinfo"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def mem_info(self) -> str:
        cmd = "cat /proc/meminfo"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def sys_info(self) -> str:
        build = "getprop ro.build.version.release"
        model = "getprop ro.product.model"
        sdk   = "getprop ro.build.version.sdk"
        if _IS_ANDROID:
            rel   = _run(build.split())
            mdl   = _run(model.split())
            sdkv  = _run(sdk.split())
        else:
            rel   = self._shell(build)
            mdl   = self._shell(model)
            sdkv  = self._shell(sdk)
        return (
            f"📱 ANDROID INFO\n"
            f"  Модель:         {mdl}\n"
            f"  Android версия: {rel}\n"
            f"  SDK уровень:    {sdkv}"
        )

    def wifi_info(self) -> str:
        if _IS_ANDROID and _cmd_available("termux-wifi-connectioninfo"):
            return _run(["termux-wifi-connectioninfo"])
        return self._shell("dumpsys wifi | grep -E 'mWifiInfo|SSID|BSSID|rssi'")

    def network_info(self) -> str:
        if _IS_ANDROID:
            return _run(["ifconfig"])
        return self._shell("ifconfig")

    # ── Системные настройки (settings) ───────────────────────────────────────
    def settings_get(self, namespace: str, key: str) -> str:
        cmd = f"settings get {namespace} {key}"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    def settings_put(self, namespace: str, key: str, value: str) -> str:
        cmd = f"settings put {namespace} {key} {value}"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)

    # ── ADB утилиты ──────────────────────────────────────────────────────────
    def adb_push(self, local: str, remote: str) -> str:
        return self._adb("push", local, remote)

    def adb_pull(self, remote: str, local: str = ".") -> str:
        return self._adb("pull", remote, local)

    def adb_logcat(self, lines: int = 50) -> str:
        return self._adb("logcat", "-d", "-t", str(lines))

    def adb_reboot(self, mode: str = "") -> str:
        cmd = ["adb", "reboot"]
        if mode in ("bootloader", "recovery", "fastboot"):
            cmd.append(mode)
        return _run(cmd)

    def screenshot(self, local_path: str = "/tmp/argos_screen.png") -> str:
        result = self._adb("exec-out", "screencap", "-p")
        if result.startswith("❌"):
            return result
        try:
            import subprocess as sp
            r = sp.run(["adb", "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=10)
            with open(local_path, "wb") as f:
                f.write(r.stdout)
            return f"✅ Скриншот сохранён: {local_path}"
        except Exception as e:
            return f"❌ Скриншот: {e}"

    def top_processes(self) -> str:
        cmd = "top -n 1 -b"
        if _IS_ANDROID:
            return _run(cmd.split())
        return self._shell(cmd)


# ══════════════════════════════════════════════════════════════════════════════
# ЕДИНЫЙ МЕНЕДЖЕР
# ══════════════════════════════════════════════════════════════════════════════

class PlatformAdmin:
    """
    Единый менеджер платформенного администрирования.
    Интегрируется в ArgosCore как core.platform_admin.
    """

    def __init__(self, core=None):
        self.core = core
        self.os   = _OS
        self.is_android = _IS_ANDROID
        self.is_termux  = _IS_TERMUX

        if _IS_ANDROID:
            self.android = AndroidAdmin()
            self.linux   = None
            self.windows = None
        elif _OS == "Linux":
            self.linux   = LinuxAdmin()
            self.android = AndroidAdmin()   # ADB-доступ к Android с ПК
            self.windows = None
        elif _OS == "Windows":
            self.windows = WindowsAdmin()
            self.android = AndroidAdmin()   # ADB-доступ к Android с ПК
            self.linux   = None
        else:
            self.linux   = None
            self.windows = None
            self.android = AndroidAdmin()

        log.info("PlatformAdmin init | OS=%s android=%s termux=%s",
                 self.os, self.is_android, self.is_termux)

    # ── Статус ────────────────────────────────────────────────────────────────
    def status(self) -> str:
        lines = ["🖥️ ПЛАТФОРМЕННЫЙ АДМИНИСТРАТОР"]
        if self.is_android:
            lines.append(f"  Платформа : Android (Termux={self.is_termux})")
            lines.append(f"  ADB       : {'✅' if _cmd_available('adb') else '❌'}")
            lines.append(f"  pkg       : {'✅' if _cmd_available('pkg') else '❌'}")
        elif self.os == "Linux":
            pm = "apt" if _cmd_available("apt-get") else ("dnf" if _cmd_available("dnf") else "pacman" if _cmd_available("pacman") else "—")
            lines.append(f"  Платформа : Linux")
            lines.append(f"  Пакет. мен: {pm}")
            lines.append(f"  systemctl : {'✅' if _cmd_available('systemctl') else '❌'}")
            lines.append(f"  ADB       : {'✅' if _cmd_available('adb') else '❌ (для Android-устройств)'}")
        elif self.os == "Windows":
            lines.append(f"  Платформа : Windows")
            lines.append(f"  winget    : {'✅' if _cmd_available('winget') else '❌'}")
            lines.append(f"  sc        : {'✅' if _cmd_available('sc') else '❌'}")
            lines.append(f"  ADB       : {'✅' if _cmd_available('adb') else '❌ (для Android-устройств)'}")
        return "\n".join(lines)

    # ── Универсальный маршрутизатор команд ───────────────────────────────────
    def handle_command(self, cmd: str) -> str:  # noqa: C901
        c = cmd.strip().lower()

        # ── Статус ───────────────────────────────────────────────────────────
        if c in ("платформа статус", "platform status", "платформа", "os статус"):
            return self.status()

        # ══════════════════════════════════════════════════
        # LINUX
        # ══════════════════════════════════════════════════
        if self.linux:
            if c.startswith("apt установи ") or c.startswith("linux установи пакет "):
                name = c.split(None, 2)[-1]
                return self.linux.pkg_install(name)
            if c.startswith("apt удали ") or c.startswith("linux удали пакет "):
                name = c.split(None, 2)[-1]
                return self.linux.pkg_remove(name)
            if c in ("apt обновить", "apt обновление", "linux обновить пакеты"):
                return self.linux.pkg_update()
            if c.startswith("apt поиск ") or c.startswith("linux поиск пакета "):
                q = c.split(None, 2)[-1]
                return self.linux.pkg_search(q)
            if c in ("apt список", "установленные пакеты linux"):
                return self.linux.pkg_list_installed()
            if c.startswith("snap установи "):
                return self.linux.snap_install(c.split(None, 2)[-1])
            if c in ("snap список", "snap list"):
                return self.linux.snap_list()
            if c.startswith("сервис запусти ") or c.startswith("systemctl start "):
                return self.linux.service_start(c.split()[-1])
            if c.startswith("сервис стоп ") or c.startswith("сервис останови ") or c.startswith("systemctl stop "):
                return self.linux.service_stop(c.split()[-1])
            if c.startswith("сервис перезапуск ") or c.startswith("systemctl restart "):
                return self.linux.service_restart(c.split()[-1])
            if c.startswith("сервис статус ") or c.startswith("systemctl status "):
                return self.linux.service_status(c.split()[-1])
            if c.startswith("сервис включи ") or c.startswith("systemctl enable "):
                return self.linux.service_enable(c.split()[-1])
            if c.startswith("сервис отключи ") or c.startswith("systemctl disable "):
                return self.linux.service_disable(c.split()[-1])
            if c in ("список сервисов", "все сервисы", "сервисы linux"):
                return self.linux.service_list()
            if c.startswith("логи "):
                unit = c.split(None, 1)[-1]
                return self.linux.logs(unit)
            if c in ("логи системы", "system logs", "journalctl"):
                return self.linux.logs()
            if c in ("диск linux", "диск использование", "df"):
                return self.linux.disk_usage()
            if c.startswith("размер папки ") or c.startswith("du "):
                path = c.split(None, 2)[-1]
                return self.linux.dir_size(path)
            if c in ("пользователь linux", "whoami linux", "linux кто я"):
                return self.linux.user_info()
            if c in ("список пользователей linux", "пользователи linux"):
                return self.linux.user_list()
            if c.startswith("добавь пользователя "):
                return self.linux.user_add(c.split()[-1])
            if c.startswith("удали пользователя "):
                return self.linux.user_del(c.split()[-1])
            if c in ("сеть linux", "ip адреса", "сетевые интерфейсы"):
                return self.linux.network_info()
            if c in ("открытые порты", "порты linux", "ss linux", "netstat linux"):
                return self.linux.ss_connections()
            if c in ("фаервол linux", "ufw статус", "firewall linux"):
                return self.linux.firewall_status()
            if c in ("система linux", "linux инфо", "linux информация"):
                return self.linux.sys_info()
            if c in ("процессор linux", "cpu linux", "lscpu"):
                return self.linux.cpu_info()
            if c in ("процессы linux", "top linux", "ps linux"):
                return self.linux.top_processes()

        # ══════════════════════════════════════════════════
        # WINDOWS
        # ══════════════════════════════════════════════════
        if self.windows:
            if c.startswith("winget установи ") or c.startswith("windows установи "):
                name = c.split(None, 2)[-1]
                return self.windows.pkg_install(name)
            if c.startswith("winget удали ") or c.startswith("windows удали "):
                name = c.split(None, 2)[-1]
                return self.windows.pkg_remove(name)
            if c in ("winget обновить", "windows обновить пакеты", "winget upgrade"):
                return self.windows.pkg_upgrade()
            if c.startswith("winget поиск "):
                return self.windows.pkg_search(c.split(None, 2)[-1])
            if c in ("winget список", "установленные пакеты windows"):
                return self.windows.pkg_list()
            if c.startswith("windows сервис запусти ") or c.startswith("sc start "):
                return self.windows.service_start(c.split()[-1])
            if c.startswith("windows сервис стоп ") or c.startswith("sc stop "):
                return self.windows.service_stop(c.split()[-1])
            if c.startswith("windows сервис статус ") or c.startswith("sc query "):
                return self.windows.service_status(c.split()[-1])
            if c in ("windows сервисы", "список сервисов windows"):
                return self.windows.service_list()
            if c.startswith("реестр запрос "):
                parts = c.split(None, 2)
                key = parts[2] if len(parts) > 2 else ""
                return self.windows.reg_query(key)
            if c in ("задачи windows", "процессы windows", "tasklist"):
                return self.windows.task_list()
            if c.startswith("убей задачу ") or c.startswith("taskkill "):
                return self.windows.task_kill(c.split()[-1])
            if c in ("сеть windows", "ipconfig", "windows сеть"):
                return self.windows.network_info()
            if c in ("фаервол windows", "windows firewall"):
                return self.windows.firewall_status()
            if c in ("обновления windows", "windows update", "windows обновления"):
                return self.windows.windows_update_check()
            if c in ("ошибки windows", "event log windows", "windows логи"):
                return self.windows.event_log()
            if c in ("диск windows", "windows диск"):
                return self.windows.disk_usage()
            if c in ("система windows", "windows инфо", "systeminfo"):
                return self.windows.sys_info()
            if c in ("defender статус", "windows defender"):
                return self.windows.defender_status()
            if c in ("defender сканировать", "defender scan"):
                return self.windows.defender_scan()
            if c in ("пользователи windows", "windows пользователи"):
                return self.windows.user_list()
            if c in ("windows кто я", "whoami windows"):
                return self.windows.user_info()

        # ══════════════════════════════════════════════════
        # ANDROID
        # ══════════════════════════════════════════════════
        if self.android:
            if c in ("adb устройства", "adb devices"):
                return self.android.adb_devices()
            if c.startswith("adb подключи "):
                host = c.split()[-1]
                return self.android.adb_connect(host)
            if c.startswith("adb отключи"):
                host = c.split()[-1] if len(c.split()) > 2 else ""
                return self.android.adb_disconnect(host)
            if c in ("android приложения", "pm list packages", "список приложений android"):
                return self.android.app_list("-3")
            if c in ("android системные приложения", "pm list system"):
                return self.android.app_list("-s")
            if c.startswith("android установи ") or c.startswith("pm install "):
                path = c.split(None, 2)[-1]
                return self.android.app_install(path)
            if c.startswith("android удали ") or c.startswith("pm uninstall "):
                pkg = c.split()[-1]
                return self.android.app_uninstall(pkg)
            if c.startswith("android запусти "):
                pkg = c.split()[-1]
                return self.android.app_start(pkg)
            if c.startswith("android останови "):
                pkg = c.split()[-1]
                return self.android.app_stop(pkg)
            if c.startswith("android очисти "):
                pkg = c.split()[-1]
                return self.android.app_clear(pkg)
            if c.startswith("pkg установи ") or c.startswith("termux установи "):
                name = c.split(None, 2)[-1]
                return self.android.termux_install(name)
            if c.startswith("pkg удали ") or c.startswith("termux удали "):
                name = c.split()[-1]
                return self.android.termux_remove(name)
            if c in ("pkg обновить", "termux обновить", "pkg update"):
                return self.android.termux_update()
            if c.startswith("pkg поиск ") or c.startswith("termux поиск "):
                return self.android.termux_search(c.split(None, 2)[-1])
            if c in ("pkg список", "termux пакеты", "termux list"):
                return self.android.termux_list()
            if c in ("android батарея", "battery status", "батарея"):
                return self.android.battery_info()
            if c in ("android хранилище", "android диск", "android storage"):
                return self.android.storage_info()
            if c in ("android инфо", "android информация", "android sys"):
                return self.android.sys_info()
            if c in ("android wifi", "android сеть", "wifi android"):
                return self.android.wifi_info()
            if c in ("android процессы", "android top"):
                return self.android.top_processes()
            if c.startswith("android настройки получить "):
                parts = c.split()
                ns = parts[-2] if len(parts) >= 2 else "system"
                key = parts[-1]
                return self.android.settings_get(ns, key)
            if c.startswith("android настройки установить "):
                parts = c.split()
                if len(parts) >= 5:
                    return self.android.settings_put(parts[-3], parts[-2], parts[-1])
                return "Формат: android настройки установить [namespace] [key] [value]"
            if c in ("android скриншот", "adb screenshot"):
                return self.android.screenshot()
            if c.startswith("adb logcat"):
                return self.android.adb_logcat()
            if c.startswith("adb push "):
                parts = c.split(None, 3)
                if len(parts) == 4:
                    return self.android.adb_push(parts[2], parts[3])
                return "Формат: adb push [локальный_файл] [удалённый_путь]"
            if c.startswith("adb pull "):
                parts = c.split(None, 3)
                remote = parts[2] if len(parts) >= 3 else ""
                local  = parts[3] if len(parts) >= 4 else "."
                return self.android.adb_pull(remote, local)
            if c in ("android перезагрузка", "adb reboot"):
                return self.android.adb_reboot()
            if c in ("android recovery", "adb reboot recovery"):
                return self.android.adb_reboot("recovery")
            if c in ("android fastboot", "adb reboot bootloader"):
                return self.android.adb_reboot("bootloader")

        return f"❓ Команда не распознана: {cmd!r}"
