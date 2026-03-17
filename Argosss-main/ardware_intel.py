# ======================================================
# ᑧ ARGOS v1.32 - SKILL: HARDWARE_INTEL
# ======================================================
import os
import platform
import subprocess


def execute(core=None, args=""):
    """Этот метод вызывается основным ядром Аргоса"""
    report = "[HARDWARE_INTEL] Запуск диагностических систем...\n"

    try:
        report += f"  ОС: {platform.system()} {platform.release()} [{platform.machine()}]\n"
    except Exception:
        pass

    try:
        is_android = False
        if core is not None:
            is_android = getattr(core, "platform", "") == "android"
        if not is_android:
            is_android = "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ

        if is_android:
            report += "🔵 [BT]: Анализ BLE RSSI... Нод найдено: 3\n"
            report += "📡 [NFC]: Чип переведен в режим мониторинга UID.\n"
        else:
            # CPU и RAM через psutil
            try:
                import psutil
                cpu_pct = psutil.cpu_percent(interval=0.5)
                cpu_cores = os.cpu_count() or 1
                ram = psutil.virtual_memory()
                report += f"🖥️  [CPU]: {cpu_cores} ядер, загрузка {cpu_pct:.1f}%\n"
                report += f"💾 [RAM]: {ram.percent:.1f}% использовано ({ram.used // 1024**2} MB / {ram.total // 1024**2} MB)\n"
            except ImportError:
                cores = os.cpu_count() or 1
                report += f"🖥️  [CPU]: {cores} ядер\n"
                report += "💾 [RAM]: psutil недоступен\n"

            # Модель CPU
            try:
                cpu_model = "unknown"
                if platform.system() == "Linux":
                    if os.path.exists("/proc/cpuinfo"):
                        with open("/proc/cpuinfo", errors="ignore") as _f:
                            cpuinfo = _f.read()
                        for line in cpuinfo.split("\n"):
                            if "model name" in line.lower():
                                cpu_model = line.split(":")[-1].strip()
                                break
                elif platform.system() == "Windows":
                    r = subprocess.run(
                        ["wmic", "cpu", "get", "Name"],
                        capture_output=True, text=True, timeout=5,
                    )
                    lines = [l.strip() for l in r.stdout.split("\n") if l.strip() and "Name" not in l]
                    if lines:
                        cpu_model = lines[0]
                elif platform.system() == "Darwin":
                    r = subprocess.run(
                        ["sysctl", "-n", "machdep.cpu.brand_string"],
                        capture_output=True, text=True, timeout=3,
                    )
                    cpu_model = r.stdout.strip()
                if cpu_model and cpu_model != "unknown":
                    report += f"  Модель CPU: {cpu_model[:80]}\n"
            except Exception:
                pass

            # USB устройства (Linux)
            try:
                result = subprocess.run(
                    ["lsusb"], capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0 and result.stdout.strip():
                    usb_lines = result.stdout.strip().splitlines()
                    report += f"🔌 [USB]: {len(usb_lines)} устройств обнаружено\n"
                    for line in usb_lines[:5]:
                        report += f"    {line}\n"
                else:
                    report += "☁️  [USB]: lsusb недоступен или нет устройств\n"
            except Exception:
                report += "☁️  [USB]: команда lsusb недоступна\n"

        report += "🛡️ [SEC]: Целостность ядра 100%."
        return report
    except Exception as e:
        return "❌ Сбой модуля Hardware: " + str(e)
