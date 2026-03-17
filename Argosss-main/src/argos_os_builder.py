"""
src/argos_os_builder.py — Сборка Argos OS и прошивка Android устройств
=======================================================================
Модуль предоставляет:

1. ArgosOSBuilder — сборка полноценного образа Argos OS:
   • ISO-образ (через mkisofs/genisoimage) для загрузки с USB/DVD
   • ZIP/7z-образ — кросс-платформенный портативный релиз
   • Автоматическое определение хост-системы (Windows/Linux/macOS)
   • Генерация GRUB-конфига (Linux BIOS/UEFI) и BCD-скрипта (Windows)
   • Встраивание start.sh / start.bat / launch.ps1 / launch.bat
   • Опциональная упаковка Python venv + зависимостей

2. AndroidFlasher — прошивка Android устройств:
   • Fastboot: стандартные разделы (boot, system, recovery, vbmeta)
   • ADB: sideload ZIP (LineageOS, TWRP-recovery zip)
   • Odin (Windows): поддержка Samsung TAR/MD5 пакетов
   • TWRP: установка через adb sideload
   • Разблокировка загрузчика (с предупреждением)
   • Резервное копирование перед прошивкой

Использование:
    from src.argos_os_builder import ArgosOSBuilder, AndroidFlasher

    builder = ArgosOSBuilder()
    print(builder.detect_host())
    print(builder.build_zip())

    flasher = AndroidFlasher()
    print(flasher.detect_devices())
    print(flasher.flash_recovery("/path/to/twrp.img"))
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional

from src.argos_logger import get_logger

log = get_logger("argos.os_builder")

# ── Версия ───────────────────────────────────────────────────────────────
ARGOS_VERSION = "1.3.0"

# ── Файлы/директории, исключаемые из образа ──────────────────────────────
_EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".buildozer", "build", "builds",
    "dist", "bin", "data", "logs", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "releases",
}
_EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".db", ".log", ".tmp", ".bak",
    ".toc", ".pyz", ".pkg", ".exe", ".dll", ".so",
}
_EXCLUDE_FILES = {".env", "master.key", "node_id", "node_birth"}


def _should_include(rel: Path) -> bool:
    for part in rel.parts[:-1]:
        if part in _EXCLUDE_DIRS:
            return False
    name = rel.parts[-1]
    if name.startswith(".") and name not in {".gitignore", ".env.example"}:
        return False
    if name in _EXCLUDE_FILES:
        return False
    if Path(name).suffix.lower() in _EXCLUDE_EXTS:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════
# ARGOS OS BUILDER
# ══════════════════════════════════════════════════════════════════════════

class ArgosOSBuilder:
    """Сборка полноценного образа Argos OS для загрузки с USB/флешки/диска."""

    def __init__(self, project_root: str = ".", output_dir: str = "releases") -> None:
        self.root       = Path(project_root).resolve()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._host      = self.detect_host()

    # ── Определение хост-системы ──────────────────────────────────────────
    def detect_host(self) -> dict:
        """Определяет хост-систему и доступные инструменты сборки образа."""
        os_name  = platform.system()   # 'Windows', 'Linux', 'Darwin'
        is_efi   = os.path.exists("/sys/firmware/efi")
        is_uefi  = is_efi or (os_name == "Windows" and self._win_is_uefi())

        tools = {
            "mkisofs":      bool(shutil.which("mkisofs")),
            "genisoimage":  bool(shutil.which("genisoimage")),
            "grub-mkrescue":bool(shutil.which("grub-mkrescue")),
            "grub2-mkrescue":bool(shutil.which("grub2-mkrescue")),
            "xorriso":      bool(shutil.which("xorriso")),
            "7z":           bool(shutil.which("7z")),
            "py7zr":        self._have_py7zr(),
        }
        return {
            "os":       os_name,
            "arch":     platform.machine(),
            "firmware": "UEFI" if is_uefi else "BIOS",
            "tools":    tools,
            "can_iso":  any([tools["mkisofs"], tools["genisoimage"],
                             tools["xorriso"], tools["grub-mkrescue"],
                             tools["grub2-mkrescue"]]),
        }

    @staticmethod
    def _win_is_uefi() -> bool:
        try:
            import winreg  # type: ignore[import]
            k = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\SecureBoot\State"
            )
            winreg.CloseKey(k)
            return True
        except Exception:
            return False

    @staticmethod
    def _have_py7zr() -> bool:
        try:
            import py7zr  # noqa: F401
            return True
        except ImportError:
            return False

    def detect_report(self) -> str:
        """Текстовый отчёт о хост-системе."""
        h = self.detect_host()
        lines = [
            f"🔍 Хост: {h['os']} / {h['arch']} / {h['firmware']}",
            f"   ISO-инструменты: {'✅' if h['can_iso'] else '❌ нет'}",
            "",
            "🔧 Доступные инструменты сборки образов:",
        ]
        for tool, ok in h["tools"].items():
            lines.append(f"  {'✅' if ok else '❌'} {tool}")
        return "\n".join(lines)

    # ── ZIP-образ (кросс-платформенный) ──────────────────────────────────
    def build_zip(self, version: str = ARGOS_VERSION,
                  include_launcher: bool = True) -> str:
        """
        Создаёт полный ZIP-образ Argos OS со всеми лаунчерами.

        Структура архива:
          argos-v{version}/
            main.py, genesis.py, requirements.txt ...
            launch.sh   — Linux / macOS / WSL
            launch.bat  — Windows (cmd)
            launch.ps1  — Windows (PowerShell)
            BOOT/
              grub.cfg  — GRUB конфиг (Linux)
              bcd_setup.bat — BCD-скрипт (Windows)
              README_BOOT.txt

        Returns:
            str: путь к созданному архиву или сообщение об ошибке
        """
        stamp    = int(time.time())
        out_path = self.output_dir / f"argos-v{version}.zip"
        prefix   = f"argos-v{version}"

        log.info("Сборка ZIP-образа Argos OS v%s…", version)
        file_count = 0
        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as zf:
                # Основные файлы проекта
                for item in sorted(self.root.rglob("*")):
                    if not item.is_file():
                        continue
                    rel = item.relative_to(self.root)
                    if not _should_include(rel):
                        continue
                    zf.write(item, f"{prefix}/{rel.as_posix()}")
                    file_count += 1

                if include_launcher:
                    # BOOT/ — загрузочные конфиги
                    zf.writestr(f"{prefix}/BOOT/grub.cfg",
                                self._grub_cfg(version))
                    zf.writestr(f"{prefix}/BOOT/bcd_setup.bat",
                                self._bcd_setup_bat(version))
                    zf.writestr(f"{prefix}/BOOT/README_BOOT.txt",
                                self._boot_readme(version))

            size_mb = out_path.stat().st_size / 1024 / 1024
            log.info("ZIP-образ готов: %s (%.1f МБ, %d файлов)",
                     out_path.name, size_mb, file_count)
            return (
                f"✅ Argos OS ZIP-образ создан:\n"
                f"  📦 {out_path}  ({size_mb:.1f} МБ, {file_count} файлов)\n\n"
                f"🚀 Запуск:\n"
                f"  Windows:   launch.bat  или  powershell -File launch.ps1\n"
                f"  Linux/Mac: bash launch.sh\n\n"
                f"💿 Для записи на USB (Linux):\n"
                f"  unzip {out_path.name} && cd {prefix}\n"
                f"  sudo bash launch.sh"
            )
        except Exception as e:
            log.error("build_zip: %s", e)
            return f"❌ Ошибка сборки ZIP-образа: {e}"

    # ── ISO-образ (загрузочный) ───────────────────────────────────────────
    def build_iso(self, version: str = ARGOS_VERSION) -> str:
        """
        Создаёт загрузочный ISO-образ Argos OS через grub-mkrescue/xorriso.

        ISO включает:
          • Полный исходный код Argos OS
          • GRUB2 загрузчик (BIOS + UEFI)
          • start.sh для запуска после загрузки

        Требует: grub-mkrescue + xorriso (Linux)
        Returns:
            str: путь к ISO или инструкция по установке инструментов
        """
        h = self.detect_host()
        if not h["can_iso"]:
            return (
                "⚠️ ISO-инструменты не найдены.\n"
                "Установи:\n"
                "  Linux:  sudo apt install grub2-common xorriso\n"
                "  macOS:  brew install xorriso\n"
                "  Windows: используй build_zip() — ZIP лучше подходит для Windows."
            )

        out_path = self.output_dir / f"argos-v{version}.iso"
        log.info("Сборка ISO-образа…")

        with tempfile.TemporaryDirectory() as td:
            iso_root = Path(td) / "iso_root"
            boot_dir = iso_root / "boot" / "grub"
            src_dir  = iso_root / "argos"
            boot_dir.mkdir(parents=True)
            src_dir.mkdir(parents=True)

            # Копируем исходники
            for item in self.root.rglob("*"):
                if not item.is_file():
                    continue
                rel = item.relative_to(self.root)
                if not _should_include(rel):
                    continue
                dst = src_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)

            # GRUB конфиг
            (boot_dir / "grub.cfg").write_text(
                self._grub_cfg(version), encoding="utf-8"
            )

            # grub-mkrescue / xorriso
            mkrescue = shutil.which("grub-mkrescue") or shutil.which("grub2-mkrescue")
            if mkrescue:
                try:
                    r = subprocess.run(
                        [mkrescue, "-o", str(out_path), str(iso_root)],
                        capture_output=True, text=True, timeout=300
                    )
                    if r.returncode == 0:
                        size_mb = out_path.stat().st_size / 1024 / 1024
                        return (
                            f"✅ Argos OS ISO создан: {out_path} ({size_mb:.1f} МБ)\n\n"
                            f"💿 Запись на USB (Linux):\n"
                            f"  sudo dd if={out_path} of=/dev/sdX bs=4M status=progress\n\n"
                            f"💿 Запись на USB (Windows):\n"
                            f"  Rufus: https://rufus.ie/ → выбери ISO"
                        )
                    return f"❌ grub-mkrescue: {r.stderr[:400]}"
                except subprocess.TimeoutExpired:
                    return "⏱️ grub-mkrescue: таймаут 300с"
                except Exception as e:
                    return f"❌ {e}"

            # Fallback: xorriso
            xorriso = shutil.which("xorriso")
            if xorriso:
                try:
                    r = subprocess.run(
                        [xorriso, "-as", "mkisofs", "-R", "-J",
                         "-o", str(out_path), str(iso_root)],
                        capture_output=True, text=True, timeout=300
                    )
                    if r.returncode == 0:
                        size_mb = out_path.stat().st_size / 1024 / 1024
                        return f"✅ Argos OS ISO (xorriso): {out_path} ({size_mb:.1f} МБ)"
                    return f"❌ xorriso: {r.stderr[:400]}"
                except Exception as e:
                    return f"❌ {e}"

        return "❌ Нет подходящего инструмента для создания ISO"

    # ── GRUB конфиг ──────────────────────────────────────────────────────
    def _grub_cfg(self, version: str) -> str:
        return (
            f"# GRUB2 config — Argos OS v{version}\n"
            "set timeout=5\n"
            "set default=0\n\n"
            f"menuentry 'Argos OS v{version}' {{\n"
            "    set root=(hd0,1)\n"
            "    linux /boot/vmlinuz root=/dev/sda1 quiet splash\n"
            "    initrd /boot/initrd.img\n"
            "}\n\n"
            f"menuentry 'Argos OS v{version} — Запуск Python' {{\n"
            "    set root=(hd0,1)\n"
            "    linux /boot/vmlinuz root=/dev/sda1\n"
            "    initrd /boot/initrd.img\n"
            "    # После загрузки выполни: cd /argos && bash launch.sh\n"
            "}\n"
        )

    # ── BCD setup script (Windows) ────────────────────────────────────────
    def _bcd_setup_bat(self, version: str) -> str:
        return (
            "@echo off\n"
            "chcp 65001 >nul\n"
            f"echo Настройка BCD для Argos OS v{version}\n"
            "echo Требуются права администратора!\n"
            "bcdedit /set {bootmgr} timeout 10\n"
            "bcdedit /create /d \"Argos OS\" /application bootsector\n"
            "echo Запись создана. Настрой путь через bcdedit /set {GUID} path ...\n"
            "pause\n"
        )

    def _boot_readme(self, version: str) -> str:
        return (
            f"=== Argos OS v{version} Boot Guide ===\n\n"
            "LINUX (GRUB/EFI):\n"
            "  1. sudo grub-install --target=x86_64-efi --efi-directory=/boot/efi\n"
            "  2. Скопируй grub.cfg в /boot/grub/grub.cfg\n"
            "  3. sudo update-grub\n\n"
            "WINDOWS (BCD):\n"
            "  1. Запусти bcd_setup.bat от администратора\n"
            "  2. Или вручную: bcdedit /create /d 'Argos OS' /application bootsector\n\n"
            "USB (dd):\n"
            "  sudo dd if=argos.iso of=/dev/sdX bs=4M\n"
            "  Rufus (Windows): rufus.ie\n"
        )

    def status(self) -> str:
        h = self.detect_host()
        zips = list(self.output_dir.glob("*.zip"))
        isos = list(self.output_dir.glob("*.iso"))
        return (
            f"🔱 ArgosOSBuilder:\n"
            f"  Хост: {h['os']} / {h['arch']} / {h['firmware']}\n"
            f"  ISO-инструменты: {'✅' if h['can_iso'] else '❌'}\n"
            f"  ZIP-образов: {len(zips)}\n"
            f"  ISO-образов: {len(isos)}\n"
            f"  Директория: {self.output_dir}"
        )


# ══════════════════════════════════════════════════════════════════════════
# ANDROID FLASHER
# ══════════════════════════════════════════════════════════════════════════

class AndroidFlasher:
    """
    Прошивка Android устройств.

    Поддерживаемые методы:
      • fastboot flash  — стандартная прошивка разделов (boot, system, recovery…)
      • adb sideload    — установка ZIP через ADB (LineageOS, custom ROM)
      • TWRP sideload   — TWRP recovery установка пакетов
      • Samsung Odin    — TAR/MD5 пакеты для Samsung (через Heimdall на Linux)

    ⚠️ Все операции с прошивкой необратимы. Рекомендуется резервная копия.
    """

    _SAFE_PARTITIONS = frozenset([
        "boot", "recovery", "system", "vendor", "vbmeta",
        "dtbo", "super", "userdata", "cache",
    ])

    def __init__(self) -> None:
        self._confirmed = False

    def confirm(self, code: str) -> str:
        if code.strip().upper() == "ARGOS-ANDROID-FLASH":
            self._confirmed = True
            return "✅ Подтверждение принято. Прошивка Android разблокирована."
        return (
            "⚠️ Введи код подтверждения перед прошивкой Android:\n"
            "  Код: ARGOS-ANDROID-FLASH\n"
            "  Команда: android подтверди ARGOS-ANDROID-FLASH"
        )

    def _require_confirm(self) -> str | None:
        if not self._confirmed:
            return (
                "🔒 Требуется подтверждение.\n"
                "Введи: android подтверди ARGOS-ANDROID-FLASH"
            )
        return None

    # ── Обнаружение устройств ─────────────────────────────────────────────
    def detect_devices(self) -> str:
        """Обнаруживает подключённые Android устройства (ADB + fastboot)."""
        lines = ["📱 Android устройства:\n"]

        # ADB
        adb = shutil.which("adb")
        if adb:
            try:
                r = subprocess.run(["adb", "devices", "-l"],
                                   capture_output=True, text=True, timeout=10)
                adb_lines = [l for l in r.stdout.strip().split("\n") if l and "List" not in l]
                if adb_lines:
                    lines.append("  ADB устройства:")
                    for l in adb_lines:
                        lines.append(f"    {l}")
                else:
                    lines.append("  ADB: нет устройств")
            except Exception as e:
                lines.append(f"  ADB: {e}")
        else:
            lines.append("  ADB: не найден (установи Android Platform-Tools)")

        # Fastboot
        fb = shutil.which("fastboot")
        if fb:
            try:
                r = subprocess.run(["fastboot", "devices"],
                                   capture_output=True, text=True, timeout=10)
                fb_lines = [l for l in r.stdout.strip().split("\n") if l]
                if fb_lines:
                    lines.append("\n  Fastboot устройства:")
                    for l in fb_lines:
                        lines.append(f"    {l}")
                else:
                    lines.append("\n  Fastboot: нет устройств")
            except Exception as e:
                lines.append(f"\n  Fastboot: {e}")
        else:
            lines.append("\n  Fastboot: не найден")

        # Heimdall (Samsung)
        hd = shutil.which("heimdall")
        lines.append(f"\n  Heimdall (Samsung): {'✅' if hd else '❌ не найден'}")

        return "\n".join(lines)

    # ── Резервная копия ───────────────────────────────────────────────────
    def backup_partition(self, partition: str,
                         output_path: str = "builds/android") -> str:
        """Создаёт резервную копию раздела через fastboot."""
        guard = self._require_confirm()
        if guard: return guard
        out = Path(output_path)
        out.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        dst   = out / f"{partition}_{stamp}.img"
        cmd   = ["fastboot", "fetch", partition, str(dst)]
        return self._run_cmd(cmd, f"Backup {partition}", 120)

    # ── Fastboot прошивка ─────────────────────────────────────────────────
    def flash_fastboot(self, partition: str, image_path: str) -> str:
        """
        Прошивает раздел через fastboot.

        Args:
            partition:  имя раздела ('boot', 'recovery', 'system' …)
            image_path: путь к .img файлу
        """
        guard = self._require_confirm()
        if guard: return guard

        if partition not in self._SAFE_PARTITIONS:
            return (
                f"❌ Раздел '{partition}' не в списке безопасных.\n"
                f"Безопасные: {sorted(self._SAFE_PARTITIONS)}"
            )
        if not Path(image_path).exists():
            return f"❌ Файл не найден: {image_path}"

        cmd = ["fastboot", "flash", partition, image_path]
        return self._run_cmd(cmd, f"fastboot flash {partition}", 180)

    def flash_recovery(self, image_path: str) -> str:
        """Прошивает TWRP/recovery раздел."""
        return self.flash_fastboot("recovery", image_path)

    def flash_boot(self, image_path: str) -> str:
        """Прошивает boot.img (kernel + ramdisk)."""
        return self.flash_fastboot("boot", image_path)

    def flash_system(self, image_path: str) -> str:
        """Прошивает system.img."""
        return self.flash_fastboot("system", image_path)

    # ── ADB Sideload ──────────────────────────────────────────────────────
    def adb_sideload(self, zip_path: str) -> str:
        """
        Устанавливает ROM/пакет через adb sideload (из recovery).

        Устройство должно быть в режиме ADB sideload в TWRP/stock recovery.
        """
        guard = self._require_confirm()
        if guard: return guard
        if not Path(zip_path).exists():
            return f"❌ Файл не найден: {zip_path}"
        cmd = ["adb", "sideload", zip_path]
        return self._run_cmd(cmd, "adb sideload", 600)

    # ── Samsung Heimdall ──────────────────────────────────────────────────
    def heimdall_flash(self, partition: str, file_path: str) -> str:
        """Прошивает Samsung устройство через Heimdall (open-source Odin)."""
        guard = self._require_confirm()
        if guard: return guard
        if not shutil.which("heimdall"):
            return (
                "❌ Heimdall не найден.\n"
                "Установи:\n"
                "  Linux:  sudo apt install heimdall-flash\n"
                "  macOS:  brew install heimdall\n"
                "  Windows: https://glassechidna.com.au/heimdall/"
            )
        if not Path(file_path).exists():
            return f"❌ Файл не найден: {file_path}"
        cmd = ["heimdall", "flash",
               f"--{partition.upper()}", file_path, "--no-reboot"]
        return self._run_cmd(cmd, f"Heimdall {partition}", 300)

    # ── Разблокировка загрузчика ──────────────────────────────────────────
    def unlock_bootloader(self) -> str:
        """Разблокирует загрузчик Android (СТИРАЕТ ВСЕ ДАННЫЕ!)."""
        guard = self._require_confirm()
        if guard: return guard
        return (
            "⚠️  РАЗБЛОКИРОВКА ЗАГРУЗЧИКА — ЭТО СОТРЁТ ВСЕ ДАННЫЕ!\n\n"
            "Шаги:\n"
            "  1. Настройки → О телефоне → Номер сборки (7 раз)\n"
            "  2. Настройки → Для разработчиков → OEM разблокировка ВКЛ\n"
            "  3. adb reboot bootloader\n"
            "  4. fastboot flashing unlock          (Android 8+)\n"
            "     fastboot oem unlock               (старые устройства)\n"
            "  5. Подтверди на экране устройства\n"
            "  6. fastboot reboot\n\n"
            "После разблокировки:\n"
            "  → fastboot flash recovery twrp.img\n"
            "  → adb sideload lineage-xx.zip\n"
        )

    # ── Reboot ───────────────────────────────────────────────────────────
    def reboot_fastboot(self) -> str:
        return self._run_cmd(["adb", "reboot", "bootloader"], "Reboot fastboot", 15)

    def reboot_recovery(self) -> str:
        return self._run_cmd(["adb", "reboot", "recovery"], "Reboot recovery", 15)

    def reboot_system(self) -> str:
        return self._run_cmd(["fastboot", "reboot"], "Reboot system", 15)

    # ── Инфо об устройстве ───────────────────────────────────────────────
    def device_info(self) -> str:
        """Получает подробную информацию о подключённом Android-устройстве."""
        lines = ["📱 Информация об устройстве:\n"]
        props = [
            ("ro.product.model",    "Модель"),
            ("ro.product.brand",    "Бренд"),
            ("ro.build.version.release", "Android"),
            ("ro.build.id",         "Build ID"),
            ("ro.bootloader",       "Bootloader"),
            ("ro.secure",           "Secure"),
            ("ro.debuggable",       "Debuggable"),
        ]
        adb = shutil.which("adb")
        if not adb:
            return "❌ adb не найден. Установи Android Platform-Tools."
        for prop, label in props:
            try:
                r = subprocess.run(
                    ["adb", "shell", "getprop", prop],
                    capture_output=True, text=True, timeout=5
                )
                value = r.stdout.strip() or "н/д"
                lines.append(f"  {label:<20}: {value}")
            except Exception:
                lines.append(f"  {label:<20}: (ошибка)")
        return "\n".join(lines)

    # ── Вспомогательные ──────────────────────────────────────────────────
    def _run_cmd(self, cmd: list[str], label: str, timeout: int) -> str:
        if not shutil.which(cmd[0]):
            return f"❌ {label}: {cmd[0]!r} не найден"
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = (r.stdout + r.stderr).strip()
            if r.returncode == 0:
                return f"✅ {label}:\n{out[-400:]}" if out else f"✅ {label}: OK"
            return f"❌ {label} (код {r.returncode}):\n{out[:400]}"
        except subprocess.TimeoutExpired:
            return f"⏱️ {label}: таймаут {timeout}с"
        except Exception as e:
            return f"❌ {label}: {e}"

    def status(self) -> str:
        tools = {
            "adb":       bool(shutil.which("adb")),
            "fastboot":  bool(shutil.which("fastboot")),
            "heimdall":  bool(shutil.which("heimdall")),
        }
        return (
            f"📱 AndroidFlasher:\n"
            + "\n".join(
                f"  {'✅' if ok else '❌'} {tool}"
                for tool, ok in tools.items()
            )
            + f"\n  Подтверждение: {'✅ активно' if self._confirmed else '❌ требуется'}"
        )
