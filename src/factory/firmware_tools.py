"""
firmware_tools.py — ARGOS Firmware Compiler & Decompiler.

Компилирует исходный код прошивок (.ino / .c / .py) и анализирует
бинарные файлы (.bin / .hex / .uf2).

Поддерживаемые платформы:
  • ESP32  — esptool + arduino-cli / platformio
  • RP2040 — platformio / picotool
  • STM32  — platformio / arm-none-eabi-gcc

Компиляция:
  прошивка компилируй [файл] [чип]      — скомпилировать исходник
  прошивка собери [файл] [чип]          — псевдоним
  прошивка установи инструменты         — авто-установка arduino-cli/platformio

Декомпиляция / анализ:
  прошивка декомпилируй [файл]          — извлечь строки, секции, мета
  прошивка анализ [файл]               — псевдоним
  прошивка инфо [файл]                 — краткая сводка .bin / .hex / .uf2

Список:
  прошивки список                       — список локальных прошивок
"""
import os
import re
import shutil
import struct
import subprocess
import sys
from datetime import datetime
from typing import Optional, Tuple

from src.argos_logger import get_logger

log = get_logger("argos.firmware_tools")

FIRMWARE_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "firmware"
))

# Расширения исходников → тип
_SRC_EXTS = {".ino": "arduino", ".c": "c", ".cpp": "cpp",
             ".py": "micropython", ".mpy": "micropython"}
_BIN_EXTS = {".bin", ".hex", ".uf2", ".elf"}


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: list, cwd: str = None, timeout: int = 300) -> Tuple[int, str]:
    """Запускает команду и возвращает (код, объединённый вывод)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, out.strip()
    except FileNotFoundError:
        return -1, f"Инструмент не найден: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, f"Таймаут ({timeout}s): {' '.join(cmd)}"
    except Exception as e:
        return -3, str(e)


def _which(*names) -> Optional[str]:
    """Возвращает первый найденный исполняемый файл из списка."""
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _auto_install(pip_package: str, check_bin: str) -> Tuple[bool, str]:
    """Устанавливает пакет через pip если инструмент не найден.

    Возвращает (успех, сообщение).
    """
    if _which(check_bin):
        return True, f"{check_bin} уже установлен"
    log.info("Авто-установка %s ...", pip_package)
    code, out = _run([sys.executable, "-m", "pip", "install", "--quiet",
                      pip_package], timeout=180)
    if code == 0 and _which(check_bin):
        return True, f"✅ {pip_package} установлен"
    # pip install прошёл, но бинарник мог попасть в ~/.local/bin
    local_bin = os.path.join(os.path.expanduser("~"), ".local", "bin", check_bin)
    if os.path.exists(local_bin):
        return True, f"✅ {pip_package} установлен → {local_bin}"
    return False, (f"❌ Не удалось установить {pip_package}.\n"
                   f"   pip вывод: {out[:300]}")


def _file_size_str(path: str) -> str:
    try:
        b = os.path.getsize(path)
        return f"{b:,} байт ({b // 1024} KB)" if b >= 1024 else f"{b} байт"
    except Exception:
        return "?"


# ─────────────────────────────────────────────────────────────────────────────
# Компилятор
# ─────────────────────────────────────────────────────────────────────────────

class FirmwareCompiler:
    """Компилирует исходный код прошивки для ESP32 / RP2040 / STM32."""

    CHIP_FQBN = {
        "esp32":  "esp32:esp32:esp32",
        "rp2040": "rp2040:rp2040:rpipico",
        "stm32":  "STMicroelectronics:stm32:GenF4",
    }

    def compile(self, source_path: str, chip: str = "esp32",
                output_dir: str = None) -> str:
        """Компилирует исходник. Возвращает строку с результатом."""
        source_path = os.path.abspath(source_path)
        if not os.path.exists(source_path):
            return f"❌ Файл не найден: {source_path}"

        ext = os.path.splitext(source_path)[1].lower()
        src_type = _SRC_EXTS.get(ext)
        if src_type is None:
            return (f"❌ Неподдерживаемый тип файла: {ext}\n"
                    f"   Поддерживаются: {', '.join(_SRC_EXTS)}")

        chip = chip.lower().strip()
        if output_dir is None:
            output_dir = os.path.join(
                FIRMWARE_DIR, "compiled",
                f"{chip}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
        os.makedirs(output_dir, exist_ok=True)

        if src_type == "micropython":
            return self._compile_micropython(source_path, chip, output_dir)
        return self._compile_arduino_or_pio(source_path, chip, output_dir)

    def _compile_arduino_or_pio(self, src: str, chip: str, out: str) -> str:
        # Попытка 1: arduino-cli
        acli = _which("arduino-cli")
        if not acli:
            ok, msg = _auto_install("arduino-cli", "arduino-cli")
            if ok:
                acli = _which("arduino-cli") or os.path.join(
                    os.path.expanduser("~"), ".local", "bin", "arduino-cli")
            else:
                log.info("arduino-cli: %s", msg)

        if acli and os.path.exists(acli):
            fqbn = self.CHIP_FQBN.get(chip, self.CHIP_FQBN["esp32"])
            src_dir = os.path.dirname(src)
            code, result = _run(
                [acli, "compile", "--fqbn", fqbn,
                 "--output-dir", out, src_dir],
                timeout=300,
            )
            if code == 0:
                bins = [f for f in os.listdir(out) if f.endswith(".bin")]
                bin_path = os.path.join(out, bins[0]) if bins else out
                return (f"✅ Скомпилировано (arduino-cli):\n"
                        f"   Чип: {chip} | FQBN: {fqbn}\n"
                        f"   Вывод: {bin_path}\n"
                        f"   Размер: {_file_size_str(bin_path) if bins else 'см. папку'}")
            log.warning("arduino-cli compile: %s", result[:200])

        # Попытка 2: platformio
        pio = _which("platformio", "pio")
        if not pio:
            ok, msg = _auto_install("platformio", "platformio")
            if ok:
                pio = _which("platformio", "pio")
            else:
                log.info("platformio: %s", msg)

        if pio:
            pio_board = {
                "esp32":  "esp32dev",
                "rp2040": "rpipico",
                "stm32":  "nucleo_f401re",
            }.get(chip, "esp32dev")
            pio_platform = {
                "esp32":  "espressif32",
                "rp2040": "raspberrypi",
                "stm32":  "ststm32",
            }.get(chip, "espressif32")
            os.makedirs(os.path.join(out, "src"), exist_ok=True)
            shutil.copy(src, os.path.join(out, "src", "main.cpp"))
            with open(os.path.join(out, "platformio.ini"), "w") as f:
                f.write(
                    f"[env:{chip}]\n"
                    f"platform = {pio_platform}\n"
                    f"board = {pio_board}\n"
                    f"framework = arduino\n"
                    f"build_dir = {out}/.pio\n"
                )
            code, result = _run([pio, "run"], cwd=out, timeout=300)
            if code == 0:
                # Ищем скомпилированный .bin в .pio/build
                bin_path = ""
                for root, _, files in os.walk(os.path.join(out, ".pio")):
                    for f in files:
                        if f.endswith(".bin"):
                            bin_path = os.path.join(root, f)
                            break
                    if bin_path:
                        break
                return (f"✅ Скомпилировано (platformio):\n"
                        f"   Чип: {chip} | board: {pio_board}\n"
                        f"   Бинарник: {bin_path or 'см. папку ' + out}\n"
                        f"   Размер: {_file_size_str(bin_path) if bin_path else '?'}")
            return f"❌ PlatformIO ошибка компиляции:\n{result[:500]}"

        # Попытка 3: ESP-IDF (только ESP32, если установлен)
        if chip == "esp32":
            idf = _which("idf.py")
            if idf:
                code, result = _run([idf, "build"], cwd=os.path.dirname(src),
                                    timeout=600)
                if code == 0:
                    return f"✅ Скомпилировано (ESP-IDF): {result[:200]}"

        return (
            f"❌ Инструменты компиляции не найдены и не удалось установить автоматически.\n"
            f"   Установите вручную один из:\n"
            f"   • arduino-cli: https://arduino.github.io/arduino-cli/latest/installation/\n"
            f"   • PlatformIO:  pip install platformio\n"
            f"   • ESP-IDF:     https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/\n"
            f"   Целевой чип: {chip} | Файл: {src}"
        )

    def _compile_micropython(self, src: str, chip: str, out: str) -> str:
        mpy_cross = _which("mpy-cross")
        if not mpy_cross:
            ok, msg = _auto_install("mpy-cross", "mpy-cross")
            if ok:
                mpy_cross = _which("mpy-cross")
            else:
                log.info("mpy-cross: %s", msg)

        if mpy_cross:
            out_file = os.path.join(out, os.path.basename(src).replace(".py", ".mpy"))
            code, result = _run([mpy_cross, src, "-o", out_file])
            if code == 0:
                return (f"✅ MicroPython скомпилирован:\n"
                        f"   {src} → {out_file}\n"
                        f"   Размер: {_file_size_str(out_file)}")
            return f"❌ mpy-cross ошибка:\n{result[:400]}"

        # Попытка через модуль Python, если pip-пакет установлен но бинарник не в PATH
        code, result = _run(
            [sys.executable, "-m", "mpy_cross", src,
             "-o", os.path.join(out, os.path.basename(src).replace(".py", ".mpy"))],
            timeout=60,
        )
        if code == 0:
            out_file = os.path.join(out, os.path.basename(src).replace(".py", ".mpy"))
            return (f"✅ MicroPython скомпилирован (python -m mpy_cross):\n"
                    f"   {src} → {out_file}\n"
                    f"   Размер: {_file_size_str(out_file)}")

        return (
            f"❌ mpy-cross не найден и не удалось установить.\n"
            f"   Установите: pip install mpy-cross\n"
            f"   Файл: {src}"
        )

    def generate_template(self, chip: str = "esp32",
                          template: str = "blink") -> str:
        """Создаёт шаблон исходника прошивки и возвращает путь к файлу."""
        chip = chip.lower().strip()
        os.makedirs(FIRMWARE_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name  = f"template_{template}_{chip}_{stamp}.ino"
        path  = os.path.join(FIRMWARE_DIR, name)

        templates = {
            "blink": (
                "// Argos Blink Template\n"
                f"// Чип: {chip}\n"
                "void setup() {\n"
                "  Serial.begin(115200);\n"
                "  pinMode(LED_BUILTIN, OUTPUT);\n"
                "  Serial.println(\"Argos Blink ready\");\n"
                "}\n\n"
                "void loop() {\n"
                "  digitalWrite(LED_BUILTIN, HIGH); delay(500);\n"
                "  digitalWrite(LED_BUILTIN, LOW);  delay(500);\n"
                "}\n"
            ),
            "sensor": (
                "// Argos Sensor Template\n"
                f"// Чип: {chip}\n"
                "void setup() {\n"
                "  Serial.begin(115200);\n"
                "  Serial.println(\"Argos Sensor ready\");\n"
                "}\n\n"
                "void loop() {\n"
                "  float temp = analogRead(A0) * 0.1;\n"
                "  Serial.print(\"T:\"); Serial.println(temp);\n"
                "  delay(1000);\n"
                "}\n"
            ),
            "mqtt": (
                "// Argos MQTT Template\n"
                f"// Чип: {chip}\n"
                "#include <WiFi.h>\n"
                "#include <PubSubClient.h>\n\n"
                "const char* ssid   = \"YOUR_SSID\";\n"
                "const char* pass   = \"YOUR_PASS\";\n"
                "const char* broker = \"192.168.1.1\";\n\n"
                "WiFiClient wifiClient;\n"
                "PubSubClient mqtt(wifiClient);\n\n"
                "void setup() {\n"
                "  Serial.begin(115200);\n"
                "  WiFi.begin(ssid, pass);\n"
                "  while (WiFi.status() != WL_CONNECTED) delay(500);\n"
                "  mqtt.setServer(broker, 1883);\n"
                "}\n\n"
                "void loop() {\n"
                "  if (!mqtt.connected()) mqtt.connect(\"argos_node\");\n"
                "  mqtt.publish(\"argos/sensor\", \"ok\");\n"
                "  mqtt.loop();\n"
                "  delay(5000);\n"
                "}\n"
            ),
        }
        code = templates.get(template, templates["blink"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return (f"✅ Шаблон создан:\n"
                f"   Тип: {template} | Чип: {chip}\n"
                f"   Файл: {path}\n"
                f"   Следующий шаг: прошивка компилируй {path} {chip}")

    @staticmethod
    def install_tools() -> str:
        """Устанавливает все доступные инструменты компиляции прошивок."""
        results = ["🔧 УСТАНОВКА ИНСТРУМЕНТОВ КОМПИЛЯЦИИ:"]
        for pip_pkg, bin_name in [
            ("platformio",  "platformio"),
            ("mpy-cross",   "mpy-cross"),
            ("esptool",     "esptool.py"),
        ]:
            ok, msg = _auto_install(pip_pkg, bin_name)
            results.append(f"  {'✅' if ok else '❌'} {pip_pkg}: {msg}")
        # arduino-cli: рекомендуем официальный скрипт
        if not _which("arduino-cli"):
            results.append(
                "  ℹ️  arduino-cli: установите вручную\n"
                "      https://arduino.github.io/arduino-cli/latest/installation/"
            )
        else:
            results.append("  ✅ arduino-cli: уже установлен")
        return "\n".join(results)


# ─────────────────────────────────────────────────────────────────────────────
# Декомпилятор / анализатор
# ─────────────────────────────────────────────────────────────────────────────

class FirmwareDecompiler:
    """Анализирует бинарные файлы прошивок (.bin / .hex / .uf2 / .elf)."""

    def analyze(self, file_path: str) -> str:
        """Анализирует прошивку и возвращает читаемый отчёт."""
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            return f"❌ Файл не найден: {file_path}"

        ext = os.path.splitext(file_path)[1].lower()
        size = _file_size_str(file_path)
        lines = [
            f"🔬 АНАЛИЗ ПРОШИВКИ: {os.path.basename(file_path)}",
            f"   Формат: {ext or 'неизвестен'} | Размер: {size}",
        ]

        if ext == ".bin":
            lines += self._analyze_bin(file_path)
        elif ext == ".hex":
            lines += self._analyze_hex(file_path)
        elif ext == ".uf2":
            lines += self._analyze_uf2(file_path)
        elif ext == ".elf":
            lines += self._analyze_elf(file_path)
        else:
            lines.append("   ⚠️ Формат не распознан, базовый анализ строк:")
            lines += self._extract_strings(file_path)

        return "\n".join(lines)

    # ── .bin ─────────────────────────────────────────────

    def _analyze_bin(self, path: str) -> list:
        result = []
        with open(path, "rb") as f:
            header = f.read(16)

        # ESP32 magic
        if header[:1] == b"\xe9":
            result.append("   📦 Тип: ESP32 прошивка (magic 0xE9)")
            chip_id = header[12:14]
            result.append(f"   Chip ID: 0x{chip_id.hex()}")
        # ARGOS stub magic
        elif header[:5] == b"ARGOS":
            version = struct.unpack("<I", header[5:9])[0]
            chip = header[9:17].rstrip(b"\x00").decode(errors="replace")
            result.append(f"   📦 Тип: ARGOS stub (v{version}, чип: {chip})")
        else:
            result.append(f"   📦 Заголовок: {header.hex()}")

        result += self._extract_strings(path, limit=15)
        return result

    def _analyze_hex(self, path: str) -> list:
        result = ["   📦 Тип: Intel HEX"]
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        addresses, data_records = [], 0
        for line in lines:
            line = line.strip()
            if not line.startswith(":"):
                continue
            rec_type = int(line[7:9], 16)
            if rec_type == 0:  # data
                data_records += 1
                addr = int(line[3:7], 16)
                addresses.append(addr)
        if addresses:
            result.append(f"   Записей данных: {data_records}")
            result.append(f"   Диапазон адресов: 0x{min(addresses):04X} – 0x{max(addresses):04X}")
        # Embedded strings
        result += self._extract_strings_from_hex(path, limit=10)
        return result

    def _analyze_uf2(self, path: str) -> list:
        result = ["   📦 Тип: UF2 (RP2040 / RP2350)"]
        with open(path, "rb") as f:
            data = f.read()
        # UF2 block = 512 bytes, magic first/last words
        MAGIC1, MAGIC2 = 0x0A324655, 0x9E5D5157
        blocks = 0
        families = set()
        for i in range(0, len(data) - 512, 512):
            m1 = struct.unpack_from("<I", data, i)[0]
            m2 = struct.unpack_from("<I", data, i + 4)[0]
            if m1 == MAGIC1 and m2 == MAGIC2:
                blocks += 1
                flags = struct.unpack_from("<I", data, i + 8)[0]
                if flags & 0x2000:  # familyID present
                    fam = struct.unpack_from("<I", data, i + 28)[0]
                    families.add(f"0x{fam:08X}")
        result.append(f"   Блоков UF2: {blocks} ({blocks * 256} байт полезных данных)")
        if families:
            fam_names = {
                "0xE48BFF56": "RP2040",
                "0xE48BFF59": "RP2350 ARM",
                "0xE48BFF5B": "RP2350 RISC-V",
            }
            for fid in families:
                result.append(f"   Family ID: {fid} ({fam_names.get(fid, 'неизвестен')})")
        return result

    def _analyze_elf(self, path: str) -> list:
        result = ["   📦 Тип: ELF бинарник"]
        # Попытка использовать readelf
        re_tool = _which("arm-none-eabi-readelf", "readelf")
        if re_tool:
            code, out = _run([re_tool, "-h", path], timeout=10)
            if code == 0:
                for ln in out.splitlines()[:12]:
                    result.append(f"   {ln.strip()}")
                return result
        # Fallback: разобрать заголовок вручную
        with open(path, "rb") as f:
            elf = f.read(64)
        if elf[:4] == b"\x7fELF":
            bits = "64-bit" if elf[4] == 2 else "32-bit"
            endian = "little" if elf[5] == 1 else "big"
            result.append(f"   Архитектура: {bits} {endian}-endian")
            machine = struct.unpack_from("<H", elf, 18)[0]
            machines = {0x28: "ARM", 0xF3: "RISC-V", 0x3E: "x86-64", 0x03: "x86"}
            result.append(f"   Machine: 0x{machine:02X} ({machines.get(machine, 'неизвестен')})")
        return result

    # ── Строки ───────────────────────────────────────────

    def _extract_strings(self, path: str, limit: int = 20) -> list:
        """Извлекает читаемые строки из бинарного файла."""
        result = ["   📝 Строки в прошивке:"]
        try:
            with open(path, "rb") as f:
                data = f.read()
            strings = re.findall(rb"[ -~]{5,}", data)
            seen, count = set(), 0
            for s in strings:
                decoded = s.decode("ascii", errors="replace")
                if decoded not in seen:
                    seen.add(decoded)
                    result.append(f"     • {decoded[:80]}")
                    count += 1
                    if count >= limit:
                        remaining = len(strings) - count
                        if remaining > 0:
                            result.append(f"     … ещё {remaining} строк")
                        break
        except Exception as e:
            result.append(f"     ⚠️ Ошибка извлечения строк: {e}")
        return result

    def _extract_strings_from_hex(self, path: str, limit: int = 10) -> list:
        """Извлекает ASCII-строки из Intel HEX файла."""
        raw_bytes = bytearray()
        try:
            with open(path, "r", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(":"):
                        byte_count = int(line[1:3], 16)
                        rec_type   = int(line[7:9], 16)
                        if rec_type == 0:
                            raw_bytes += bytes.fromhex(line[9:9 + byte_count * 2])
        except Exception:
            pass
        strings = re.findall(rb"[ -~]{5,}", raw_bytes)
        if not strings:
            return []
        result = ["   📝 Строки:"]
        for s in strings[:limit]:
            result.append(f"     • {s.decode('ascii', errors='replace')[:80]}")
        return result

    def disassemble(self, file_path: str) -> str:
        """Пробует дизассемблировать ELF через objdump."""
        file_path = os.path.abspath(file_path)
        if not file_path.endswith(".elf"):
            return "⚠️ Дизассемблирование доступно только для .elf файлов."
        objdump = _which("arm-none-eabi-objdump", "objdump")
        if not objdump:
            return ("❌ arm-none-eabi-objdump не найден.\n"
                    "   Установите: sudo apt install gcc-arm-none-eabi\n"
                    "   или: brew install arm-none-eabi-gcc")
        code, out = _run([objdump, "-d", "--no-show-raw-insn",
                          "--demangle", file_path], timeout=60)
        if code != 0:
            return f"❌ objdump error:\n{out[:400]}"
        lines = out.splitlines()[:80]
        return "🔩 ДИЗАССЕМБЛИРОВАНИЕ (первые 80 строк):\n" + "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Единый фасад
# ─────────────────────────────────────────────────────────────────────────────

class FirmwareTools:
    """Фасад: компилятор + декомпилятор прошивок."""

    def __init__(self):
        self.compiler   = FirmwareCompiler()
        self.decompiler = FirmwareDecompiler()

    def list_firmwares(self) -> str:
        """Список всех локальных прошивок."""
        os.makedirs(FIRMWARE_DIR, exist_ok=True)
        exts = _BIN_EXTS | set(_SRC_EXTS.keys())
        files = [f for f in os.listdir(FIRMWARE_DIR)
                 if os.path.splitext(f)[1].lower() in exts]
        if not files:
            return f"📁 {FIRMWARE_DIR}: прошивок нет.\nЗагрузи: обнови тасмота"
        lines = [f"📁 Прошивки ({FIRMWARE_DIR}):"]
        for fname in sorted(files):
            fpath = os.path.join(FIRMWARE_DIR, fname)
            lines.append(f"  • {fname}  {_file_size_str(fpath)}")
        return "\n".join(lines)

    def compile(self, source_path: str, chip: str = "esp32") -> str:
        return self.compiler.compile(source_path, chip)

    def generate_template(self, chip: str = "esp32",
                          template: str = "blink") -> str:
        return self.compiler.generate_template(chip, template)

    def analyze(self, file_path: str) -> str:
        return self.decompiler.analyze(file_path)

    def disassemble(self, file_path: str) -> str:
        return self.decompiler.disassemble(file_path)
