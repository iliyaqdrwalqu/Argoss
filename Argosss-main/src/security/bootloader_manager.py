"""
bootloader_manager.py — Управление загрузчиком (своё устройство)
  Windows: bcdedit, EFI entries, BCD, Windows Service
  Linux:   GRUB, systemd-boot, EFI, initramfs
  Android: fastboot, TWRP

  ⚠️ Все операции требуют явного подтверждения пользователя.
"""
import os
import re
import sys
import platform
import subprocess
import json

OS = platform.system()


class BootloaderManager:
    def __init__(self):
        self.os_type    = OS
        self.is_android = "ANDROID_ROOT" in os.environ
        self._confirmed = False  # Флаг подтверждения пользователя

    # ══════════════════════════════════════════════════════
    # ПОДТВЕРЖДЕНИЕ — без него ничего не работает
    # ══════════════════════════════════════════════════════
    def confirm(self, code: str) -> str:
        """Пользователь должен ввести код подтверждения перед опасными операциями."""
        expected = "ARGOS-BOOT-CONFIRM"
        if code.strip().upper() == expected:
            self._confirmed = True
            return "✅ Подтверждение принято. Операции с загрузчиком разблокированы."
        return (
            f"⚠️ Введи код подтверждения для операций с загрузчиком:\n"
            f"  Код: {expected}\n"
            f"  Команда: подтверди {expected}"
        )

    def _require_confirm(self) -> str | None:
        if not self._confirmed:
            return (
                "🔒 Операция заблокирована. Требуется подтверждение.\n"
                "Введи: подтверди ARGOS-BOOT-CONFIRM"
            )
        return None

    # ══════════════════════════════════════════════════════
    # ОПРЕДЕЛЕНИЕ СИСТЕМЫ
    # ══════════════════════════════════════════════════════
    def detect_system(self) -> dict:
        """Определяет тип ОС, прошивки и загрузчика.

        Returns:
            dict с полями:
              os         — 'Windows' | 'Linux' | 'Android' | 'Darwin'
              firmware   — 'UEFI' | 'BIOS' | 'unknown'
              bootloader — 'BCD' | 'GRUB' | 'GRUB2' | 'systemd-boot' | 'fastboot' | 'unknown'
              arch       — 'x86_64' | 'arm64' | ...
              details    — dict с дополнительной информацией
        """
        result: dict = {
            "os":         self.os_type if not self.is_android else "Android",
            "firmware":   "unknown",
            "bootloader": "unknown",
            "arch":       platform.machine(),
            "details":    {},
        }

        if self.is_android:
            result["firmware"]   = "BIOS"
            result["bootloader"] = "fastboot"
            try:
                r = subprocess.run(["getprop", "ro.bootloader"],
                                   capture_output=True, text=True, timeout=3)
                result["details"]["bootloader_version"] = r.stdout.strip()
            except Exception:
                pass
            return result

        if self.os_type == "Windows":
            result["firmware"]   = "UEFI" if self._check_windows_efi() else "BIOS"
            result["bootloader"] = "BCD"
            result["details"]["bcd_ok"] = self._probe_bcdedit()
            return result

        if self.os_type == "Linux":
            result["firmware"] = "UEFI" if os.path.exists("/sys/firmware/efi") else "BIOS"
            # Определяем загрузчик
            if os.path.exists("/boot/grub2/grub.cfg"):
                result["bootloader"] = "GRUB2"
                result["details"]["grub_cfg"] = "/boot/grub2/grub.cfg"
            elif os.path.exists("/boot/grub/grub.cfg"):
                result["bootloader"] = "GRUB"
                result["details"]["grub_cfg"] = "/boot/grub/grub.cfg"
            elif os.path.exists("/boot/loader"):
                result["bootloader"] = "systemd-boot"
            else:
                result["bootloader"] = "unknown"
            # Доп. инфо
            result["details"]["efi_vars"] = os.path.exists("/sys/firmware/efi/efivars")
            result["details"]["efi_dir"]  = "/boot/efi" if os.path.isdir("/boot/efi") else None
            return result

        if self.os_type == "Darwin":
            result["firmware"]   = "UEFI"
            result["bootloader"] = "unknown"  # Apple Silicon / Intel EFI
            return result

        return result

    def detect_system_report(self) -> str:
        """Текстовый отчёт detect_system() для вывода пользователю."""
        d = self.detect_system()
        fw_icon  = "🔵" if d["firmware"] == "UEFI" else "🟡"
        os_icons = {"Windows": "🖥️", "Linux": "🐧", "Android": "📱", "Darwin": "🍎"}
        lines = [
            f"{os_icons.get(d['os'], '💻')} Система: {d['os']}  {fw_icon} Прошивка: {d['firmware']}",
            f"⚙️  Загрузчик: {d['bootloader']}    🏗️  Архитектура: {d['arch']}",
        ]
        for k, v in d.get("details", {}).items():
            if v is not None:
                lines.append(f"  • {k}: {v}")
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════
    # ОБЩАЯ ИНФОРМАЦИЯ О ЗАГРУЗЧИКЕ
    # ══════════════════════════════════════════════════════
    def get_boot_info(self) -> str:
        if self.is_android:
            return self._android_boot_info()
        if self.os_type == "Windows":
            return self._windows_boot_info()
        return self._linux_boot_info()

    def _windows_boot_info(self) -> str:
        try:
            r = subprocess.run(
                ["bcdedit", "/enum", "all"],
                capture_output=True, text=True, encoding="cp866", timeout=10
            )
            lines = r.stdout.strip().split("\n")[:40]
            efi   = self._check_windows_efi()
            return (
                f"🖥️ ЗАГРУЗЧИК Windows:\n"
                f"  Тип: {'UEFI/EFI' if efi else 'Legacy BIOS/MBR'}\n\n"
                + "\n".join(lines[:25])
            )
        except Exception as e:
            return f"❌ bcdedit недоступен: {e}"

    def _check_windows_efi(self) -> bool:
        """Проверяет UEFI через наличие EFI системной переменной окружения."""
        # Надёжный метод: проверить наличие EFI-переменных через реестр
        try:
            import winreg  # type: ignore[import]
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\SecureBoot\State",
            )
            winreg.CloseKey(key)
            return True  # ключ существует только на UEFI системах
        except Exception:
            pass
        # Запасной метод: проверить bcdedit /enum firmware
        return self._probe_bcdedit_firmware()

    def _probe_bcdedit(self) -> bool:
        try:
            r = subprocess.run(["bcdedit"], capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def _probe_bcdedit_firmware(self) -> bool:
        try:
            r = subprocess.run(
                ["bcdedit", "/enum", "{fwbootmgr}"],
                capture_output=True, text=True, timeout=5
            )
            return r.returncode == 0
        except Exception:
            return False

    def _linux_boot_info(self) -> str:
        info = self.detect_system()
        lines = [f"🐧 ЗАГРУЗЧИК Linux — {info['firmware']} / {info['bootloader']}:"]

        if info["firmware"] == "UEFI":
            try:
                r = subprocess.run(
                    ["efibootmgr", "-v"],
                    capture_output=True, text=True, timeout=5
                )
                lines.append("\n📋 EFI записи:")
                lines.extend("  " + l for l in r.stdout.split("\n")[:20])
            except FileNotFoundError:
                lines.append("  (efibootmgr не установлен: sudo apt install efibootmgr)")

        grub_cfg = info["details"].get("grub_cfg")
        if grub_cfg:
            lines.append(f"\n✅ {info['bootloader']} конфиг: {grub_cfg}")
        else:
            lines.append("\n⚠️ GRUB конфиг не найден")

        return "\n".join(lines)

    def _android_boot_info(self) -> str:
        lines = ["📱 Android ЗАГРУЗЧИК:"]
        try:
            r = subprocess.run(
                ["getprop", "ro.bootloader"],
                capture_output=True, text=True, timeout=3
            )
            lines.append(f"  Версия: {r.stdout.strip()}")
        except Exception:
            lines.append("  (getprop недоступен)")
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════
    # WINDOWS — BCD и EFI
    # ══════════════════════════════════════════════════════
    def windows_add_boot_entry(self, label: str, path: str) -> str:
        guard = self._require_confirm()
        if guard: return guard
        try:
            r = subprocess.run(
                ["bcdedit", "/create", "/d", label, "/application", "bootsector"],
                capture_output=True, text=True, timeout=10
            )
            guid_match = re.search(r"\{[a-f0-9-]+\}", r.stdout)
            if not guid_match:
                return f"❌ Не удалось создать BCD-запись:\n{r.stdout}"
            g = guid_match.group()
            subprocess.run(["bcdedit", "/set", g, "device", f"partition={path}"],
                           capture_output=True, timeout=10)
            subprocess.run(["bcdedit", "/set", g, "path", r"\argos\bootmgr"],
                           capture_output=True, timeout=10)
            subprocess.run(["bcdedit", "/displayorder", g, "/addlast"],
                           capture_output=True, timeout=10)
            return f"✅ BCD запись создана: {label} ({g})"
        except Exception as e:
            return f"❌ BCD ошибка: {e}"

    def windows_set_timeout(self, seconds: int) -> str:
        guard = self._require_confirm()
        if guard: return guard
        try:
            subprocess.run(
                ["bcdedit", "/timeout", str(seconds)],
                capture_output=True, text=True, check=True, timeout=10
            )
            return f"✅ Таймаут загрузки: {seconds}с"
        except Exception as e:
            return f"❌ {e}"

    def windows_set_default(self, entry_id: str) -> str:
        guard = self._require_confirm()
        if guard: return guard
        try:
            subprocess.run(["bcdedit", "/default", entry_id],
                           check=True, capture_output=True, timeout=10)
            return f"✅ Запись по умолчанию изменена: {entry_id}"
        except Exception as e:
            return f"❌ {e}"

    # ══════════════════════════════════════════════════════
    # LINUX — GRUB и EFI
    # ══════════════════════════════════════════════════════
    def linux_update_grub(self) -> str:
        guard = self._require_confirm()
        if guard: return guard
        candidates = [
            ["update-grub"],
            ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"],
            ["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"],
        ]
        for cmd in candidates:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    return f"✅ GRUB обновлён:\n{r.stdout[-200:]}"
            except FileNotFoundError:
                continue
        return "❌ update-grub не найден. Попробуй: sudo grub-mkconfig -o /boot/grub/grub.cfg"

    def linux_install_grub(self, device: str = "/dev/sda") -> str:
        guard = self._require_confirm()
        if guard: return guard
        try:
            is_efi = os.path.exists("/sys/firmware/efi")
            if is_efi:
                cmd = ["sudo", "grub-install", "--target=x86_64-efi",
                       "--efi-directory=/boot/efi", "--bootloader-id=ARGOS"]
            else:
                cmd = ["sudo", "grub-install", device]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return f"✅ GRUB установлен на {device}"
            return f"❌ grub-install:\n{r.stderr[:300]}"
        except Exception as e:
            return f"❌ {e}"

    def linux_add_efi_entry(self, label: str, loader: str,
                            disk: str = "/dev/sda", part: int = 1) -> str:
        guard = self._require_confirm()
        if guard: return guard
        try:
            r = subprocess.run(
                ["sudo", "efibootmgr", "-c",
                 "-d", disk, "-p", str(part),
                 "-L", label, "-l", loader],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                return f"✅ EFI-запись добавлена: {label}"
            return f"❌ efibootmgr:\n{r.stderr[:300]}"
        except Exception as e:
            return f"❌ {e}"

    def linux_set_grub_default(self, entry: str) -> str:
        guard = self._require_confirm()
        if guard: return guard
        try:
            subprocess.run(["sudo", "grub-set-default", entry],
                           check=True, timeout=10)
            return f"✅ GRUB по умолчанию: {entry}"
        except Exception as e:
            return f"❌ {e}"

    def linux_add_grub_entry(self, name: str, kernel: str,
                              initrd: str, params: str = "quiet splash") -> str:
        guard = self._require_confirm()
        if guard: return guard
        custom = "/etc/grub.d/40_custom"
        entry  = (
            f"\nmenuentry '{name}' {{\n"
            f"    linux {kernel} {params}\n"
            f"    initrd {initrd}\n"
            f"}}\n"
        )
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".grub", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(entry)
                tmp_path = tmp.name
            # Дописываем в файл через sudo tee -a (избегаем прямой записи root-файла)
            subprocess.run(
                ["sudo", "tee", "-a", custom],
                stdin=open(tmp_path), capture_output=True, timeout=10
            )
            os.unlink(tmp_path)
            self.linux_update_grub()
            return f"✅ GRUB-запись '{name}' добавлена"
        except Exception as e:
            return f"❌ {e}"

    # ══════════════════════════════════════════════════════
    # ANDROID — fastboot и TWRP
    # ══════════════════════════════════════════════════════
    def android_fastboot_info(self) -> str:
        try:
            r = subprocess.run(
                ["fastboot", "getvar", "all"],
                capture_output=True, text=True, timeout=10
            )
            return f"📱 Fastboot:\n{r.stderr[:500]}"
        except Exception as e:
            return (
                f"❌ fastboot недоступен: {e}\n"
                "Устройство должно быть в режиме Fastboot:\n"
                "  adb reboot bootloader"
            )

    def android_unlock_bootloader(self) -> str:
        guard = self._require_confirm()
        if guard: return guard
        return (
            "📱 Разблокировка загрузчика Android:\n\n"
            "⚠️ ЭТО СОТРЁТ ВСЕ ДАННЫЕ НА УСТРОЙСТВЕ!\n\n"
            "Шаги:\n"
            "  1. Включи OEM Unlock: Настройки → Для разработчиков\n"
            "  2. adb reboot bootloader\n"
            "  3. fastboot oem unlock\n"
            "     или: fastboot flashing unlock (Pixel/новые устройства)\n"
            "  4. Подтверди на экране устройства\n"
            "  5. fastboot reboot\n\n"
            "После разблокировки:\n"
            "  → Устанавливай TWRP: fastboot flash recovery twrp.img\n"
            "  → Устанавливай Magisk для root"
        )

    def android_flash_image(self, partition: str, img_path: str) -> str:
        guard = self._require_confirm()
        if guard: return guard
        if not os.path.exists(img_path):
            return f"❌ Файл не найден: {img_path}"
        safe_parts = ["recovery", "boot", "system", "vendor", "vbmeta"]
        if partition not in safe_parts:
            return f"❌ Раздел '{partition}' не в списке безопасных: {safe_parts}"
        try:
            r = subprocess.run(
                ["fastboot", "flash", partition, img_path],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode == 0:
                return f"✅ {partition} прошит: {img_path}"
            return f"❌ Fastboot ошибка:\n{r.stderr[:300]}"
        except Exception as e:
            return f"❌ {e}"

    # ══════════════════════════════════════════════════════
    # PERSISTENCE — Аргос ниже уровня ОС
    # ══════════════════════════════════════════════════════
    def install_persistence(self) -> str:
        guard = self._require_confirm()
        if guard: return guard

        results = []

        if self.os_type == "Windows":
            # 1. Winlogon — запуск при входе пользователя
            try:
                import winreg  # type: ignore[import]
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
                    0, winreg.KEY_SET_VALUE
                )
                py  = sys.executable
                scr = os.path.join(os.path.abspath("."), "main.py")
                winreg.SetValueEx(key, "Userinit", 0, winreg.REG_SZ,
                                  f"userinit.exe, {py} \"{scr}\" --no-gui,")
                winreg.CloseKey(key)
                results.append("✅ Windows: Winlogon persistence установлена")
            except Exception as e:
                results.append(f"⚠️ Winlogon: {e}")

            # 2. Windows Service (SCM)  — правильный синтаксис sc.exe
            try:
                py  = sys.executable
                scr = os.path.join(os.path.abspath("."), "main.py")
                bin_path = f'"{py}" "{scr}" --no-gui'
                subprocess.run(
                    ["sc", "create", "ArgosCore",
                     f"binPath={bin_path}",
                     "start=", "auto",
                     "DisplayName=", "Argos Universal Core"],
                    capture_output=True, timeout=15
                )
                subprocess.run(
                    ["sc", "description", "ArgosCore",
                     "Argos Universal OS — System Intelligence"],
                    capture_output=True, timeout=10
                )
                subprocess.run(["sc", "start", "ArgosCore"],
                               capture_output=True, timeout=15)
                results.append("✅ Windows: SCM сервис зарегистрирован")
            except Exception as e:
                results.append(f"⚠️ SCM: {e}")

        elif self.os_type == "Linux":
            py  = sys.executable
            scr = os.path.abspath("main.py")

            # 1. systemd (уровень system — до монтирования /home)
            svc = (
                "[Unit]\n"
                "Description=Argos Universal OS Core\n"
                "DefaultDependencies=no\n"
                "After=sysinit.target\n\n"
                "[Service]\n"
                f"Type=simple\n"
                f"ExecStart={py} {scr} --no-gui\n"
                "Restart=always\n"
                "RestartSec=5\n\n"
                "[Install]\n"
                "WantedBy=sysinit.target\n"
            )
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".service", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(svc)
                    tmp_path = tmp.name
                subprocess.run(
                    ["sudo", "cp", tmp_path, "/etc/systemd/system/argos_core.service"],
                    capture_output=True, timeout=10
                )
                os.unlink(tmp_path)
                subprocess.run(["sudo", "systemctl", "daemon-reload"],
                               capture_output=True, timeout=15)
                subprocess.run(["sudo", "systemctl", "enable", "argos_core"],
                               capture_output=True, timeout=10)
                subprocess.run(["sudo", "systemctl", "start",  "argos_core"],
                               capture_output=True, timeout=15)
                results.append("✅ Linux: systemd persistence (sysinit.target)")
            except Exception as e:
                results.append(f"⚠️ systemd: {e}")

            # 2. rc.local (совместимость со старыми системами)
            try:
                rc   = "/etc/rc.local"
                line = f"{py} {scr} --no-gui &\n"
                if os.path.exists(rc):
                    content = open(rc).read()
                    if "argos" not in content.lower():
                        content = content.replace("exit 0", line + "exit 0")
                        import tempfile
                        with tempfile.NamedTemporaryFile(
                            mode="w", suffix=".rc", delete=False, encoding="utf-8"
                        ) as tmp:
                            tmp.write(content)
                            tmp_path = tmp.name
                        subprocess.run(
                            ["sudo", "cp", tmp_path, rc],
                            capture_output=True, timeout=10
                        )
                        os.unlink(tmp_path)
                        results.append("✅ Linux: rc.local запись добавлена")
                    else:
                        results.append("✅ Linux: rc.local уже содержит запись")
                else:
                    results.append("⚠️ rc.local не найден")
            except Exception as e:
                results.append(f"⚠️ rc.local: {e}")

            # 3. initramfs hook — самый ранний уровень (до монтирования root)
            hook = (
                "#!/bin/sh\n"
                "# Argos initramfs pre-mount hook\n"
                'PREREQS=""\n'
                'prereqs() { echo "$PREREQS"; }\n'
                "case $1 in\n"
                "  prereqs) prereqs; exit 0 ;;\n"
                "esac\n"
                ". /usr/share/initramfs-tools/hook-functions\n"
                '# Аргос стартует на этапе initramfs (до монтирования root)\n'
                'echo "[ARGOS]: Pre-mount hook active" >> /dev/kmsg\n'
            )
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".sh", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(hook)
                    tmp_path = tmp.name
                hook_dest = "/etc/initramfs-tools/scripts/init-premount/argos"
                subprocess.run(["sudo", "cp", tmp_path, hook_dest],
                               capture_output=True, timeout=10)
                os.unlink(tmp_path)
                subprocess.run(["sudo", "chmod", "+x", hook_dest],
                               capture_output=True, timeout=5)
                subprocess.run(["sudo", "update-initramfs", "-u"],
                               capture_output=True, timeout=120)
                results.append("✅ Linux: initramfs hook (pre-mount уровень)")
            except Exception as e:
                results.append(f"⚠️ initramfs: {e}")

        return "\n".join(results) or "Persistence установлена."

    # ══════════════════════════════════════════════════════
    # ПОЛНЫЙ ОТЧЁТ
    # ══════════════════════════════════════════════════════
    def full_report(self) -> str:
        return (
            self.detect_system_report() + "\n\n" +
            self.get_boot_info() + "\n\n" +
            f"🔒 Подтверждение: {'✅ Активно' if self._confirmed else '❌ Требуется'}\n"
            f"Для разблокировки: подтверди ARGOS-BOOT-CONFIRM"
        )



