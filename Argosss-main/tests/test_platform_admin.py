"""Tests for src/platform_admin.py — Linux / Windows / Android admin functions."""
import sys
import os
import platform
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.platform_admin import (
    PlatformAdmin,
    LinuxAdmin,
    WindowsAdmin,
    AndroidAdmin,
    _run,
    _cmd_available,
    _OS,
    _IS_ANDROID,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_manager():
    return PlatformAdmin(core=None)


# ── PlatformAdmin ─────────────────────────────────────────────────────────────

def test_platform_admin_init():
    mgr = make_manager()
    assert mgr.os in ("Linux", "Windows", "Darwin", "")
    assert mgr.android is not None


def test_platform_admin_status_returns_string():
    mgr = make_manager()
    result = mgr.status()
    assert isinstance(result, str)
    assert len(result) > 0


def test_handle_command_status():
    mgr = make_manager()
    result = mgr.handle_command("платформа статус")
    assert isinstance(result, str)
    assert "ПЛАТФОРМЕННЫЙ АДМИНИСТРАТОР" in result


def test_handle_command_unknown():
    mgr = make_manager()
    result = mgr.handle_command("zzz_nonexistent_command_xyz")
    assert isinstance(result, str)
    assert "не распознана" in result or "❓" in result


# ── _run helper ───────────────────────────────────────────────────────────────

def test_run_returns_string():
    result = _run(["echo", "hello"])
    assert isinstance(result, str)
    assert "hello" in result


def test_run_missing_command():
    result = _run(["_nonexistent_cmd_xyz_12345_"])
    assert isinstance(result, str)
    assert "❌" in result or "не найдена" in result.lower() or "not found" in result.lower()


def test_run_timeout():
    result = _run(["sleep", "100"], timeout=1)
    assert isinstance(result, str)
    assert "⏱" in result or "Таймаут" in result


# ── _cmd_available ────────────────────────────────────────────────────────────

def test_cmd_available_echo():
    assert _cmd_available("echo") is True


def test_cmd_available_missing():
    assert _cmd_available("_no_such_cmd_xyz_9999_") is False


# ── AndroidAdmin (ADB access — works on any platform) ────────────────────────

def test_android_admin_init():
    a = AndroidAdmin()
    assert a is not None


def test_android_admin_devices_graceful():
    """adb devices returns a string (may say ADB not found or show device list)."""
    a = AndroidAdmin()
    result = a.adb_devices()
    assert isinstance(result, str)


def test_android_admin_app_list_graceful():
    a = AndroidAdmin()
    result = a.app_list("-3")
    assert isinstance(result, str)


def test_android_admin_battery_graceful():
    a = AndroidAdmin()
    result = a.battery_info()
    assert isinstance(result, str)


def test_android_admin_storage_graceful():
    a = AndroidAdmin()
    result = a.storage_info()
    assert isinstance(result, str)


def test_android_admin_sys_info_graceful():
    a = AndroidAdmin()
    result = a.sys_info()
    assert isinstance(result, str)
    assert "ANDROID INFO" in result


def test_android_admin_termux_install_graceful():
    a = AndroidAdmin()
    result = a.termux_install("wget")
    assert isinstance(result, str)


def test_android_admin_termux_update_graceful():
    a = AndroidAdmin()
    result = a.termux_update()
    assert isinstance(result, str)


# ── LinuxAdmin (only run on Linux) ───────────────────────────────────────────

def _skip_non_linux():
    if _OS != "Linux" or _IS_ANDROID:
        import pytest
        pytest.skip("Linux only")


def test_linux_admin_init():
    a = LinuxAdmin()
    assert a is not None


def test_linux_admin_disk_usage():
    _skip_non_linux()
    a = LinuxAdmin()
    result = a.disk_usage()
    assert isinstance(result, str)
    assert len(result) > 0


def test_linux_admin_user_info():
    _skip_non_linux()
    a = LinuxAdmin()
    result = a.user_info()
    assert isinstance(result, str)
    assert "👤" in result


def test_linux_admin_network_info():
    _skip_non_linux()
    a = LinuxAdmin()
    result = a.network_info()
    assert isinstance(result, str)


def test_linux_admin_pkg_search_graceful():
    _skip_non_linux()
    a = LinuxAdmin()
    result = a.pkg_search("python3")
    assert isinstance(result, str)


def test_linux_admin_top_processes():
    _skip_non_linux()
    a = LinuxAdmin()
    result = a.top_processes(5)
    assert isinstance(result, str)


def test_linux_admin_sys_info():
    _skip_non_linux()
    a = LinuxAdmin()
    result = a.sys_info()
    assert isinstance(result, str)
    assert len(result) > 10


# ── WindowsAdmin (only instantiate, don't run commands) ──────────────────────

def test_windows_admin_init():
    a = WindowsAdmin()
    assert a is not None


# ── Platform command routing ──────────────────────────────────────────────────

def test_handle_adb_devices():
    mgr = make_manager()
    result = mgr.handle_command("adb устройства")
    assert isinstance(result, str)


def test_handle_android_battery():
    mgr = make_manager()
    result = mgr.handle_command("android батарея")
    assert isinstance(result, str)


def test_handle_android_info():
    mgr = make_manager()
    result = mgr.handle_command("android инфо")
    assert isinstance(result, str)
    assert "ANDROID INFO" in result


def test_handle_android_apps():
    mgr = make_manager()
    result = mgr.handle_command("android приложения")
    assert isinstance(result, str)


def test_handle_android_termux_update():
    mgr = make_manager()
    result = mgr.handle_command("pkg обновить")
    assert isinstance(result, str)


def test_handle_linux_disk_on_linux():
    if _OS != "Linux" or _IS_ANDROID:
        return
    mgr = make_manager()
    result = mgr.handle_command("диск linux")
    assert isinstance(result, str)


def test_handle_linux_user_info_on_linux():
    if _OS != "Linux" or _IS_ANDROID:
        return
    mgr = make_manager()
    result = mgr.handle_command("пользователь linux")
    assert isinstance(result, str)
    assert "👤" in result


def test_handle_linux_processes_on_linux():
    if _OS != "Linux" or _IS_ANDROID:
        return
    mgr = make_manager()
    result = mgr.handle_command("процессы linux")
    assert isinstance(result, str)
