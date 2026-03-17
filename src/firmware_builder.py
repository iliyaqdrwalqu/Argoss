"""
src/firmware_builder.py — Сборка и дизассемблирование прошивок для носимых устройств
======================================================================================
Поддерживаемые платформы:
  • ESP32 / ESP8266  — esptool + PlatformIO / arduino-cli
  • AVR / Arduino    — avr-gcc + avrdude
  • ARM Cortex-M     — arm-none-eabi-gcc + OpenOCD / pyOCD (STM32, nRF52, RP2040)
  • Nordic nRF52     — nrfutil + mergehex
  • Raspberry Pi RP2040 — picotool + UF2

Дизассемблирование:
  • capstone          — мульти-архитектурный дизассемблер (x86, ARM, AVR, MIPS, RISC-V)
  • objdump           — системный дизассемблер

Использование:
    from src.firmware_builder import FirmwareBuilder
    fb = FirmwareBuilder()
    print(fb.detect_toolchains())
    print(fb.compile_asm("ADD r0, r1, r2", arch="arm_thumb"))
    print(fb.disassemble_file("firmware.bin", arch="arm_thumb"))
    print(fb.flash("firmware.bin", port="/dev/ttyUSB0", target="esp32"))
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from src.argos_logger import get_logger

log = get_logger("argos.firmware")

# ── Capstone (дизассемблер) ───────────────────────────────────────────────
try:
    import capstone
    HAVE_CAPSTONE = True
except ImportError:
    capstone = None  # type: ignore[assignment]
    HAVE_CAPSTONE = False

# ── Keystone (ассемблер) ─────────────────────────────────────────────────
try:
    import keystone as ks_mod
    HAVE_KEYSTONE = True
except ImportError:
    ks_mod = None  # type: ignore[assignment]
    HAVE_KEYSTONE = False


# ══════════════════════════════════════════════════════════════════════════
# ТАБЛИЦЫ АРХИТЕКТУР
# ══════════════════════════════════════════════════════════════════════════

# Keystone arch/mode
KS_ARCH_MAP: dict[str, tuple] = {}
if HAVE_KEYSTONE:
    KS_ARCH_MAP = {
        "x86":       (ks_mod.KS_ARCH_X86,  ks_mod.KS_MODE_32),
        "x86_64":    (ks_mod.KS_ARCH_X86,  ks_mod.KS_MODE_64),
        "arm":       (ks_mod.KS_ARCH_ARM,   ks_mod.KS_MODE_ARM),
        "arm_thumb": (ks_mod.KS_ARCH_ARM,   ks_mod.KS_MODE_THUMB),
        "arm64":     (ks_mod.KS_ARCH_ARM64, ks_mod.KS_MODE_LITTLE_ENDIAN),
        "avr":       (ks_mod.KS_ARCH_AVR,   ks_mod.KS_MODE_AVR32),
        "mips":      (ks_mod.KS_ARCH_MIPS,  ks_mod.KS_MODE_MIPS32),
    }

# Capstone arch/mode
CS_ARCH_MAP: dict[str, tuple] = {}
if HAVE_CAPSTONE:
    CS_ARCH_MAP = {
        "x86":       (capstone.CS_ARCH_X86,   capstone.CS_MODE_32),
        "x86_64":    (capstone.CS_ARCH_X86,   capstone.CS_MODE_64),
        "arm":       (capstone.CS_ARCH_ARM,    capstone.CS_MODE_ARM),
        "arm_thumb": (capstone.CS_ARCH_ARM,    capstone.CS_MODE_THUMB),
        "arm64":     (capstone.CS_ARCH_ARM64,  capstone.CS_MODE_ARM),
        "avr":       (capstone.CS_ARCH_AVR,    capstone.CS_MODE_AVR),
        "mips":      (capstone.CS_ARCH_MIPS,   capstone.CS_MODE_MIPS32 | capstone.CS_MODE_BIG_ENDIAN),
    }

# Платформы носимых → архитектура ассемблера
WEARABLE_ARCH: dict[str, str] = {
    "esp32":   "xtensa",    # Xtensa LX6 — нет в keystone/capstone → используем objdump
    "esp8266": "xtensa",
    "stm32":   "arm_thumb", # ARM Cortex-M (Thumb-2)
    "nrf52":   "arm_thumb", # ARM Cortex-M4
    "rp2040":  "arm_thumb", # ARM Cortex-M0+
    "avr":     "avr",
    "arduino": "avr",
    "samd21":  "arm_thumb", # Adafruit M0
    "samd51":  "arm_thumb", # Adafruit M4
}


# ══════════════════════════════════════════════════════════════════════════
# FIRMWARE BUILDER
# ══════════════════════════════════════════════════════════════════════════

class FirmwareBuilder:
    """Компиляция, дизассемблирование и прошивка носимых устройств."""

    def __init__(self, work_dir: str = "builds/firmware") -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    # ── Инструментарий ────────────────────────────────────────────────────
    def detect_toolchains(self) -> str:
        """Определяет установленные инструменты сборки и дизассемблирования."""
        tools = [
            ("esptool",         "esptool.py",            "ESP32/ESP8266"),
            ("avrdude",         "avrdude",               "Arduino/AVR flash"),
            ("avr-gcc",         "avr-gcc",               "AVR compiler"),
            ("arm-none-eabi-gcc","arm-none-eabi-gcc",    "ARM Cortex-M compiler"),
            ("arm-none-eabi-objdump","arm-none-eabi-objdump","ARM disassembler"),
            ("nrfutil",         "nrfutil",               "Nordic nRF52"),
            ("picotool",        "picotool",              "RP2040"),
            ("openocd",         "openocd",               "OpenOCD debugger"),
            ("pyocd",           "pyocd",                 "pyOCD debugger"),
            ("platformio",      "pio",                   "PlatformIO"),
            ("arduino-cli",     "arduino-cli",           "Arduino CLI"),
            ("objdump",         "objdump",               "System disassembler"),
        ]
        lines = ["🔧 Доступные инструменты прошивок:\n"]
        for label, cmd, desc in tools:
            found = shutil.which(cmd)
            icon  = "✅" if found else "❌"
            path  = found or "не найден"
            lines.append(f"  {icon} {label:<26} {desc}  →  {path}")

        lines.append("\n📦 Python-библиотеки:")
        lines.append(f"  {'✅' if HAVE_KEYSTONE else '❌'} keystone-engine    (ассемблер: x86, ARM, AVR, MIPS)")
        lines.append(f"  {'✅' if HAVE_CAPSTONE else '❌'} capstone           (дизассемблер: x86, ARM, AVR, MIPS)")

        return "\n".join(lines)

    # ── Ассемблирование ───────────────────────────────────────────────────
    def compile_asm(self, source: str, arch: str = "arm_thumb") -> dict:
        """
        Компилирует ASM-исходник в машинный код через Keystone.

        Args:
            source: текст ASM-кода (строка)
            arch:   целевая архитектура ('arm_thumb', 'avr', 'x86_64', ...)

        Returns:
            dict: {ok, arch, bytes_hex, bytes_count, listing, error}
        """
        result: dict = {"ok": False, "arch": arch, "bytes_hex": "",
                        "bytes_count": 0, "listing": "", "error": ""}

        if not HAVE_KEYSTONE:
            result["error"] = "Keystone не установлен: pip install keystone-engine"
            return result

        if arch not in KS_ARCH_MAP:
            # Архитектура не поддерживается Keystone — пробуем системный ассемблер
            return self._compile_asm_system(source, arch)

        ks_arch, ks_mode = KS_ARCH_MAP[arch]
        try:
            ks = ks_mod.Ks(ks_arch, ks_mode)
            encoding, count = ks.asm(source)
            code_bytes = bytes(encoding)
            # Листинг: hex + ASCII preview
            hex_str  = " ".join(f"{b:02x}" for b in code_bytes)
            listing  = self._make_listing(source, code_bytes, arch)
            result.update({
                "ok":          True,
                "bytes_hex":   code_bytes.hex(),
                "bytes_count": len(code_bytes),
                "listing":     listing,
            })
            log.info("Compiled %s: %d bytes", arch, len(code_bytes))
        except Exception as e:
            result["error"] = str(e)
            log.error("compile_asm(%s): %s", arch, e)
        return result

    def compile_asm_file(self, path: str, arch: str = "arm_thumb") -> dict:
        """Компилирует .asm / .s файл."""
        try:
            source = Path(path).read_text(encoding="utf-8")
            return self.compile_asm(source, arch)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _compile_asm_system(self, source: str, arch: str) -> dict:
        """Fallback: системный ассемблер (arm-none-eabi-as, avr-as, as)."""
        result: dict = {"ok": False, "arch": arch, "bytes_hex": "",
                        "bytes_count": 0, "listing": "", "error": ""}
        arch_tools = {
            "xtensa": "xtensa-lx106-elf-as",
            "riscv":  "riscv32-unknown-elf-as",
        }
        cmd = arch_tools.get(arch, "as")
        with tempfile.TemporaryDirectory() as td:
            src_file = os.path.join(td, "input.s")
            out_file = os.path.join(td, "output.o")
            Path(src_file).write_text(source, encoding="utf-8")
            try:
                r = subprocess.run(
                    [cmd, "-o", out_file, src_file],
                    capture_output=True, text=True, timeout=30
                )
                if r.returncode != 0:
                    result["error"] = f"{cmd}: {r.stderr[:300]}"
                    return result
                data = Path(out_file).read_bytes()
                result.update({
                    "ok": True, "bytes_hex": data.hex(),
                    "bytes_count": len(data),
                    "listing": f"Assembled via {cmd}: {len(data)} bytes",
                })
            except FileNotFoundError:
                result["error"] = f"Ассемблер {cmd!r} не найден"
        return result

    # ── Дизассемблирование ────────────────────────────────────────────────
    def disassemble(self, code: bytes, arch: str = "arm_thumb",
                    base_addr: int = 0) -> str:
        """
        Дизассемблирует машинный код через Capstone.

        Args:
            code:      бинарные данные
            arch:      архитектура ('arm_thumb', 'avr', 'x86_64', ...)
            base_addr: базовый адрес для отображения

        Returns:
            Листинг дизассемблирования
        """
        if not HAVE_CAPSTONE:
            return "⚠️ Capstone не установлен: pip install capstone"

        if arch not in CS_ARCH_MAP:
            return self._disassemble_system(code, arch)

        cs_arch, cs_mode = CS_ARCH_MAP[arch]
        try:
            md = capstone.Cs(cs_arch, cs_mode)
            md.detail = False
            lines = [f"; Дизассемблирование {arch}  ({len(code)} байт)\n"]
            for instr in md.disasm(code, base_addr):
                hex_bytes = " ".join(f"{b:02x}" for b in instr.bytes)
                lines.append(
                    f"  0x{instr.address:08x}:  {hex_bytes:<24}  {instr.mnemonic} {instr.op_str}"
                )
            if len(lines) == 1:
                lines.append("  (нет инструкций)")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка дизассемблирования: {e}"

    def disassemble_hex(self, hex_str: str, arch: str = "arm_thumb",
                        base_addr: int = 0) -> str:
        """Дизассемблирует hex-строку (например 'e0 2e 00 00')."""
        try:
            code = bytes.fromhex(hex_str.replace(" ", "").replace("\n", ""))
            return self.disassemble(code, arch, base_addr)
        except Exception as e:
            return f"❌ Некорректный hex: {e}"

    def disassemble_file(self, path: str, arch: str = "arm_thumb",
                         base_addr: int = 0, max_bytes: int = 65536) -> str:
        """Дизассемблирует бинарный файл (firmware.bin, .elf, .hex)."""
        fp = Path(path)
        if not fp.exists():
            return f"❌ Файл не найден: {path}"
        # .elf / .hex — используем objdump
        if fp.suffix.lower() in (".elf", ".out"):
            return self._disassemble_elf(str(fp), arch)
        data = fp.read_bytes()[:max_bytes]
        result = self.disassemble(data, arch, base_addr)
        return f"; Файл: {fp.name}  ({fp.stat().st_size} байт)\n" + result

    def _disassemble_elf(self, path: str, arch: str) -> str:
        """Дизассемблирует ELF через arm-none-eabi-objdump или objdump."""
        objdumps = []
        if "arm" in arch:
            objdumps.append("arm-none-eabi-objdump")
        objdumps += ["avr-objdump", "objdump"]
        for tool in objdumps:
            if shutil.which(tool):
                try:
                    r = subprocess.run(
                        [tool, "-d", "-C", path],
                        capture_output=True, text=True, timeout=30
                    )
                    if r.returncode == 0:
                        # Ограничиваем вывод
                        lines = r.stdout.split("\n")[:200]
                        return f"; ELF disassembly via {tool}\n" + "\n".join(lines)
                except Exception:
                    pass
        return self._disassemble_system(Path(path).read_bytes(), arch)

    def _disassemble_system(self, code: bytes, arch: str) -> str:
        """Дизассемблирование через системный objdump."""
        objdump = shutil.which("objdump")
        if not objdump:
            return "❌ Capstone и objdump не доступны. Установи: pip install capstone"
        with tempfile.TemporaryDirectory() as td:
            bin_file = os.path.join(td, "fw.bin")
            Path(bin_file).write_bytes(code if isinstance(code, bytes) else b"")
            try:
                r = subprocess.run(
                    [objdump, "-b", "binary", "-m", "arm", "-D", bin_file],
                    capture_output=True, text=True, timeout=15
                )
                return r.stdout[:3000] if r.returncode == 0 else f"❌ objdump: {r.stderr[:200]}"
            except Exception as e:
                return f"❌ {e}"

    # ── Компиляция C/C++ для носимых ──────────────────────────────────────
    def compile_c(self, source: str, target: str = "stm32",
                  extra_flags: str = "") -> dict:
        """
        Компилирует C-код для указанной платформы носимых устройств.

        Args:
            source:      текст C-кода
            target:      платформа ('stm32', 'avr', 'nrf52', 'rp2040', ...)
            extra_flags: дополнительные флаги компилятора

        Returns:
            dict: {ok, target, elf_path, size, error}
        """
        result: dict = {"ok": False, "target": target, "elf_path": "", "size": 0, "error": ""}

        compiler_map = {
            "stm32":   "arm-none-eabi-gcc",
            "nrf52":   "arm-none-eabi-gcc",
            "rp2040":  "arm-none-eabi-gcc",
            "samd21":  "arm-none-eabi-gcc",
            "samd51":  "arm-none-eabi-gcc",
            "avr":     "avr-gcc",
            "arduino": "avr-gcc",
        }
        flag_map = {
            "stm32":   "-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16",
            "nrf52":   "-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16",
            "rp2040":  "-mcpu=cortex-m0plus -mthumb",
            "samd21":  "-mcpu=cortex-m0plus -mthumb",
            "samd51":  "-mcpu=cortex-m4 -mthumb -mfloat-abi=hard",
            "avr":     "-mmcu=atmega328p -DF_CPU=16000000UL",
            "arduino": "-mmcu=atmega328p -DF_CPU=16000000UL",
        }

        compiler = compiler_map.get(target, "arm-none-eabi-gcc")
        if not shutil.which(compiler):
            result["error"] = f"Компилятор не найден: {compiler}. Установи arm-none-eabi-gcc или avr-gcc."
            return result

        flags = flag_map.get(target, "-mcpu=cortex-m0plus -mthumb")
        if extra_flags:
            flags += " " + extra_flags

        with tempfile.TemporaryDirectory() as td:
            src_file = os.path.join(td, "main.c")
            elf_file = os.path.join(td, "firmware.elf")
            Path(src_file).write_text(source, encoding="utf-8")
            cmd = f"{compiler} {flags} -Os -o {elf_file} {src_file}"
            try:
                r = subprocess.run(
                    cmd.split(), capture_output=True, text=True, timeout=60
                )
                if r.returncode != 0:
                    result["error"] = r.stderr[:500]
                    return result
                # Копируем в work_dir
                out_dir  = self.work_dir / target
                out_dir.mkdir(parents=True, exist_ok=True)
                stamp    = int(time.time())
                out_path = out_dir / f"firmware_{stamp}.elf"
                import shutil as _sh
                _sh.copy2(elf_file, out_path)
                size = out_path.stat().st_size
                result.update({"ok": True, "elf_path": str(out_path), "size": size})
                log.info("Compiled %s: %s (%d bytes)", target, out_path.name, size)
            except Exception as e:
                result["error"] = str(e)
        return result

    # ── Прошивка устройств ────────────────────────────────────────────────
    def flash(self, firmware_path: str, port: str, target: str = "esp32",
              baud: int = 0) -> str:
        """
        Прошивает носимое устройство.

        Args:
            firmware_path: путь к .bin / .elf / .hex файлу
            port:          COM/tty порт ('COM3', '/dev/ttyUSB0')
            target:        платформа ('esp32', 'avr', 'stm32', 'nrf52', 'rp2040')
            baud:          скорость (0 = авто)

        Returns:
            str: результат прошивки
        """
        fp = Path(firmware_path)
        if not fp.exists():
            return f"❌ Файл прошивки не найден: {firmware_path}"

        flashers = {
            "esp32":   self._flash_esp32,
            "esp8266": self._flash_esp32,
            "avr":     self._flash_avr,
            "arduino": self._flash_avr,
            "stm32":   self._flash_stm32,
            "nrf52":   self._flash_nrf52,
            "rp2040":  self._flash_rp2040,
        }
        flasher = flashers.get(target)
        if not flasher:
            return f"❌ Неизвестная платформа: {target}. Поддерживаются: {list(flashers)}"
        return flasher(str(fp), port, baud)

    def _flash_esp32(self, fw: str, port: str, baud: int) -> str:
        b = str(baud) if baud else "921600"
        cmd = ["esptool.py", "--port", port, "--baud", b,
               "write_flash", "-z", "0x0", fw]
        return self._run_flash(cmd, "ESP32/ESP8266", 120)

    def _flash_avr(self, fw: str, port: str, baud: int) -> str:
        b = str(baud) if baud else "115200"
        cmd = ["avrdude", "-p", "m328p", "-c", "arduino",
               "-P", port, "-b", b, "-U", f"flash:w:{fw}:i"]
        return self._run_flash(cmd, "AVR/Arduino", 60)

    def _flash_stm32(self, fw: str, port: str, baud: int) -> str:
        # OpenOCD (JTAG/SWD) или STM32CubeProgrammer
        openocd = shutil.which("openocd")
        if openocd:
            cmd = [openocd, "-f", "interface/stlink.cfg",
                   "-f", "target/stm32f4x.cfg",
                   "-c", f"program {fw} verify reset exit"]
            return self._run_flash(cmd, "STM32 OpenOCD", 60)
        stm32cp = shutil.which("STM32_Programmer_CLI") or shutil.which("stm32flash")
        if stm32cp:
            cmd = [stm32cp, "-c", f"port={port}", "-w", fw, "-v", "-rst"]
            return self._run_flash(cmd, "STM32 Flash", 60)
        return "❌ openocd или STM32_Programmer_CLI не найден"

    def _flash_nrf52(self, fw: str, port: str, baud: int) -> str:
        nrfutil = shutil.which("nrfutil")
        if nrfutil:
            cmd = [nrfutil, "dfu", "serial", "-pkg", fw, "-p", port, "-b", "115200"]
            return self._run_flash(cmd, "nRF52 DFU", 120)
        # Fallback: openocd
        openocd = shutil.which("openocd")
        if openocd:
            cmd = [openocd, "-f", "interface/jlink.cfg",
                   "-f", "target/nrf52.cfg",
                   "-c", f"program {fw} verify reset exit"]
            return self._run_flash(cmd, "nRF52 OpenOCD", 60)
        return "❌ nrfutil или openocd не найден"

    def _flash_rp2040(self, fw: str, port: str, baud: int) -> str:
        # RP2040 поддерживает UF2 (drag-and-drop) или picotool
        picotool = shutil.which("picotool")
        if picotool:
            cmd = [picotool, "load", "-f", fw, "--update"]
            return self._run_flash(cmd, "RP2040 picotool", 30)
        # Если .uf2 — копируем на виртуальный диск
        if fw.endswith(".uf2"):
            return (
                "💡 RP2040: удерживай BOOTSEL при подключении USB,\n"
                f"   затем скопируй {fw} на появившийся диск RPI-RP2.\n"
                "   Или установи picotool: https://github.com/raspberrypi/picotool"
            )
        return "❌ picotool не найден. Для RP2040: pip install picotool или используй UF2."

    def _run_flash(self, cmd: list[str], label: str, timeout: int) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return f"✅ {label}: прошивка успешна\n{r.stdout[-300:]}"
            return f"❌ {label} (код {r.returncode}):\n{r.stderr[:400]}"
        except FileNotFoundError:
            return f"❌ {label}: инструмент не найден — {cmd[0]}"
        except subprocess.TimeoutExpired:
            return f"⏱️ {label}: таймаут {timeout}с — устройство не отвечает"
        except Exception as e:
            return f"❌ {label}: {e}"

    # ── PlatformIO ────────────────────────────────────────────────────────
    def platformio_build(self, project_dir: str, env: str = "") -> str:
        """Сборка PlatformIO проекта."""
        if not shutil.which("pio"):
            return "❌ PlatformIO не найден: pip install platformio"
        cmd = ["pio", "run"]
        if env:
            cmd += ["-e", env]
        try:
            r = subprocess.run(cmd, cwd=project_dir,
                               capture_output=True, text=True, timeout=300)
            tail = "\n".join((r.stdout + r.stderr).split("\n")[-30:])
            return (f"✅ PlatformIO build OK\n{tail}" if r.returncode == 0
                    else f"❌ PlatformIO build failed\n{tail}")
        except FileNotFoundError:
            return "❌ pio не найден: pip install platformio"
        except Exception as e:
            return f"❌ {e}"

    def platformio_flash(self, project_dir: str, env: str = "") -> str:
        """Прошивка через PlatformIO."""
        if not shutil.which("pio"):
            return "❌ PlatformIO не найден: pip install platformio"
        cmd = ["pio", "run", "-t", "upload"]
        if env:
            cmd += ["-e", env]
        try:
            r = subprocess.run(cmd, cwd=project_dir,
                               capture_output=True, text=True, timeout=180)
            tail = "\n".join((r.stdout + r.stderr).split("\n")[-20:])
            return (f"✅ PlatformIO upload OK\n{tail}" if r.returncode == 0
                    else f"❌ PlatformIO upload failed\n{tail}")
        except Exception as e:
            return f"❌ {e}"

    # ── Анализ бинарника ─────────────────────────────────────────────────
    def analyze_binary(self, path: str) -> str:
        """Анализирует бинарный файл прошивки: размер, энтропия, строки."""
        fp = Path(path)
        if not fp.exists():
            return f"❌ Файл не найден: {path}"
        data = fp.read_bytes()
        size = len(data)
        # Энтропия Шеннона
        entropy = self._shannon_entropy(data)
        # Строки ASCII
        strings = self._extract_strings(data, min_len=4)[:20]
        lines = [
            f"📊 Анализ прошивки: {fp.name}",
            f"  Размер:   {size:,} байт ({size/1024:.1f} КБ)",
            f"  Энтропия: {entropy:.3f} бит/байт  {'(возможно сжат/зашифрован)' if entropy > 7.5 else ''}",
            f"  Строки ({len(strings)}):",
        ]
        for s in strings:
            lines.append(f"    {s!r}")
        return "\n".join(lines)

    @staticmethod
    def _shannon_entropy(data: bytes) -> float:
        import math
        if not data:
            return 0.0
        freq: dict[int, int] = {}
        for b in data:
            freq[b] = freq.get(b, 0) + 1
        n = len(data)
        return -sum((c/n) * math.log2(c/n) for c in freq.values())

    @staticmethod
    def _extract_strings(data: bytes, min_len: int = 4) -> list[str]:
        result, cur = [], []
        for b in data:
            if 0x20 <= b < 0x7F:
                cur.append(chr(b))
            else:
                if len(cur) >= min_len:
                    result.append("".join(cur))
                cur = []
        return result

    # ── Утилиты ──────────────────────────────────────────────────────────
    def _make_listing(self, source: str, code: bytes, arch: str) -> str:
        """Текстовый листинг: исходник + hex + дизассемблирование."""
        lines  = [f"; Архитектура: {arch}   Байт: {len(code)}\n"]
        hex_lines = [code[i:i+16].hex(" ") for i in range(0, len(code), 16)]
        lines.append("; Машинный код (hex):")
        lines.extend(f"  {h}" for h in hex_lines)
        if HAVE_CAPSTONE and arch in CS_ARCH_MAP:
            lines.append("\n; Дизассемблирование:")
            disasm = self.disassemble(code, arch)
            lines.append(disasm)
        return "\n".join(lines)

    def status(self) -> str:
        """Краткий статус модуля прошивок."""
        images = list(self.work_dir.rglob("*.elf")) + list(self.work_dir.rglob("*.bin"))
        return (
            f"💾 FirmwareBuilder:\n"
            f"  Keystone: {'✅' if HAVE_KEYSTONE else '❌ pip install keystone-engine'}\n"
            f"  Capstone: {'✅' if HAVE_CAPSTONE else '❌ pip install capstone'}\n"
            f"  Образов в {self.work_dir}: {len(images)}\n"
            f"  Платформы: {', '.join(WEARABLE_ARCH.keys())}"
        )
