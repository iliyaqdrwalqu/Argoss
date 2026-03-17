"""
syscalls.py — низкоуровневые системные вызовы через ctypes.
  Linux: syscall/getpid + ioctl(TIOCGWINSZ)
  Windows: WinAPI через kernel32
"""
import os
import platform
import ctypes
import ctypes.util
from ctypes import wintypes


class ArgosSyscalls:
    def __init__(self):
        self.os_type = platform.system()

    def status(self) -> str:
        if self.os_type == "Windows":
            return self._windows_status()
        return self._linux_status()

    def terminal_size(self) -> str:
        if self.os_type == "Windows":
            return self._windows_terminal_size()
        return self._linux_terminal_size()

    def process_identity(self) -> str:
        if self.os_type == "Windows":
            return self._windows_process_identity()
        return self._linux_process_identity()

    # ── Linux ────────────────────────────────────────────
    def _linux_status(self) -> str:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        # x86_64 Linux: SYS_getpid = 39
        SYS_GETPID = 39
        pid = libc.syscall(SYS_GETPID)
        return (
            "🐧 ctypes/syscall (Linux):\n"
            f"  getpid(syscall): {pid}\n"
            f"  getpid(os):      {os.getpid()}"
        )

    def _linux_process_identity(self) -> str:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        SYS_GETPID = 39
        pid = int(libc.syscall(SYS_GETPID))
        uid = os.getuid() if hasattr(os, "getuid") else -1
        euid = os.geteuid() if hasattr(os, "geteuid") else -1
        return f"PID={pid}, UID={uid}, EUID={euid}"

    def _linux_terminal_size(self) -> str:
        """
        Использует ioctl(TIOCGWINSZ) для получения размеров терминала.
        Прямой вызов libc.ioctl.
        """
        try:
            # Пытаемся загрузить libc
            libc_name = ctypes.util.find_library("c")
            if not libc_name:
                return "❌ libc не найдена"
            libc = ctypes.CDLL(libc_name, use_errno=True)
        except Exception as e:
            return f"❌ Ошибка загрузки libc: {e}"

        # TIOCGWINSZ = 0x5413 на x86/x64 Linux.
        # На других архитектурах может отличаться (напр. MIPS, Sparc).
        TIOCGWINSZ = 0x5413

        class WinSize(ctypes.Structure):
            _fields_ = [
                ("ws_row", ctypes.c_ushort),
                ("ws_col", ctypes.c_ushort),
                ("ws_xpixel", ctypes.c_ushort),
                ("ws_ypixel", ctypes.c_ushort),
            ]

        ws = WinSize()
        # 0: stdin, 1: stdout, 2: stderr. Пробуем stdout.
        fd = 1 
        
        # Prototype: int ioctl(int fd, unsigned long request, ...);
        ioctl_func = libc.ioctl
        ioctl_func.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(WinSize)]
        ioctl_func.restype = ctypes.c_int

        ret = ioctl_func(fd, TIOCGWINSZ, ctypes.byref(ws))
        
        if ret != 0:
            errno = ctypes.get_errno()
            return f"❌ ioctl ошибка (errno={errno})"

        return f"📐 Терминал: {ws.ws_col}x{ws.ws_row} (ioctl прямой вызов)"

    # ── Windows ──────────────────────────────────────────
    def _windows_status(self) -> str:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        pid = kernel32.GetCurrentProcessId()
        tick = kernel32.GetTickCount64()
        return (
            "🪟 ctypes/WinAPI (Windows):\n"
            f"  GetCurrentProcessId: {pid}\n"
            f"  GetTickCount64:      {tick}"
        )

    def _windows_process_identity(self) -> str:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        pid = kernel32.GetCurrentProcessId()
        tid = kernel32.GetCurrentThreadId()
        return f"PID={pid}, TID={tid}"

    def _windows_terminal_size(self) -> str:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [
                ("Left", ctypes.c_short),
                ("Top", ctypes.c_short),
                ("Right", ctypes.c_short),
                ("Bottom", ctypes.c_short),
            ]

        class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", wintypes.WORD),
                ("srWindow", SMALL_RECT),
                ("dwMaximumWindowSize", COORD),
            ]

        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        info = CONSOLE_SCREEN_BUFFER_INFO()
        ok = kernel32.GetConsoleScreenBufferInfo(h, ctypes.byref(info))
        if not ok:
            err = ctypes.get_last_error()
            return f"❌ GetConsoleScreenBufferInfo: {err}"
        cols = info.srWindow.Right - info.srWindow.Left + 1
        rows = info.srWindow.Bottom - info.srWindow.Top + 1
        return f"📐 Консоль: {cols}x{rows} (WinAPI)"
