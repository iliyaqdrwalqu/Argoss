"""
replicator.py — 7z-репликация системы Argos.
Создаёт снимки состояния (data/config) и полные реплики (код + данные)
в формате .7z (LZMA2) для максимального сжатия.
"""
import os
import zipfile
import datetime
import shutil
try:
    import py7zr
    _PY7ZR_OK = True
except ImportError:
    py7zr = None
    _PY7ZR_OK = False
from src.argos_logger import get_logger

log = get_logger("argos.replicator")


class Replicator:
    def __init__(self):
        self.snapshot_dir = "builds/snapshots"
        self.replica_dir = "builds/replicas"
        self.image_dir = "builds/images"
        os.makedirs(self.snapshot_dir, exist_ok=True)
        os.makedirs(self.replica_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)

    def create_snapshot(self, label: str = "auto") -> str:
        """Создаёт снимок состояния системы (БД + конфиги) в формате .7z."""
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{label}_{stamp}.7z"
        filepath = os.path.join(self.snapshot_dir, filename)
        targets = ["data", "config", "logs"]
        if not _PY7ZR_OK:
            return "❌ py7zr не установлен: pip install py7zr"
        try:
            with py7zr.SevenZipFile(filepath, mode="w") as zf:
                for target in targets:
                    if os.path.exists(target):
                        for root, dirs, files in os.walk(target):
                            if "__pycache__" in root:
                                continue
                            for file in files:
                                fp = os.path.join(root, file)
                                arcname = os.path.relpath(fp, ".")
                                zf.write(fp, arcname)
            size_kb = os.path.getsize(filepath) / 1024
            log.info("Snapshot: %s (%.1f KB)", filename, size_kb)
            return f"✅ Снимок создан: {filename} ({size_kb:.1f} KB)"
        except Exception as e:
            return f"❌ Ошибка снимка: {e}"

    def rollback(self, snapshot_file: str) -> str:
        """Откат к снимку (.7z или .zip)."""
        path = os.path.join(self.snapshot_dir, snapshot_file)
        if not os.path.exists(path):
            return f"❌ Снимок не найден: {snapshot_file}"
        try:
            self.create_snapshot(label="pre_rollback")
            if snapshot_file.endswith(".7z"):
                if not _PY7ZR_OK:
                    return "❌ py7zr не установлен: pip install py7zr"
                with py7zr.SevenZipFile(path, mode="r") as zf:
                    zf.extractall(".")
            else:
                with zipfile.ZipFile(path, "r") as zf:
                    zf.extractall(".")
            return f"♻️ Откат к: {snapshot_file}"
        except Exception as e:
            return f"❌ Откат: {e}"

    def list_snapshots(self) -> list:
        try:
            return sorted(os.listdir(self.snapshot_dir), reverse=True)
        except Exception:
            return []

    def create_replica(self) -> str:
        """Создаёт полную 7z-копию системы (исходный код + данные)."""
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        archive_path = os.path.join(self.replica_dir, f"Argos_Replica_{stamp}.7z")
        exclude = {"__pycache__", ".git", "builds", "logs", "venv", ".venv",
                   "snapshot", "node_modules", ".pytest_cache", "dist"}
        if not _PY7ZR_OK:
            return "❌ py7zr не установлен: pip install py7zr"
        try:
            with py7zr.SevenZipFile(archive_path, mode="w") as zf:
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in exclude]
                    for file in files:
                        fp = os.path.join(root, file)
                        arcname = os.path.relpath(fp, ".")
                        try:
                            zf.write(fp, arcname)
                        except Exception:
                            pass
            size_mb = os.path.getsize(archive_path) / 1024 / 1024
            log.info("Replica: %s (%.1f MB)", archive_path, size_mb)
            return f"✅ Реплика создана: {archive_path} ({size_mb:.1f} MB)"
        except Exception as e:
            return f"❌ Реплика: {e}"

    def sync_to_node(self, ip: str, port: int = 22,
                     user: str = "argos", key_path: str = None) -> str:
        """Синхронизирует реплику на удалённую ноду через rsync/scp."""
        replica_files = sorted(os.listdir(self.replica_dir), reverse=True)
        if not replica_files:
            r = self.create_replica()
            if "❌" in r:
                return r
            replica_files = sorted(os.listdir(self.replica_dir), reverse=True)

        latest = os.path.join(self.replica_dir, replica_files[0])
        key_arg = f"-i {key_path}" if key_path else ""
        cmd = f"scp {key_arg} -P {port} {latest} {user}@{ip}:/tmp/"
        import subprocess
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=120)
            if r.returncode == 0:
                return f"✅ Реплика отправлена на {ip}:{port}"
            return f"❌ scp: {r.stderr[:200]}"
        except Exception as e:
            return f"❌ sync_to_node: {e}"

    def create_os_image(self) -> str:
        """Создаёт образ Argos OS — полный клон системы с загрузочным скриптом.

        Образ содержит весь исходный код, данные, конфигурации и
        start.sh / start.bat для немедленного запуска на целевой машине.
        Результат: builds/images/ArgosOS_Image_<stamp>.7z
        """
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = f"ArgosOS_Image_{stamp}.7z"
        image_path = os.path.join(self.image_dir, image_name)

        exclude = {
            "__pycache__", ".git", "builds", "logs", "venv", ".venv",
            "snapshot", "node_modules", ".pytest_cache", "dist",
        }

        # Загрузочные скрипты, которые добавляются прямо в архив
        boot_sh = (
            "#!/usr/bin/env bash\n"
            "# Argos OS — boot script\n"
            "set -e\n"
            "cd \"$(dirname \"$0\")\"\n"
            "if [ ! -d venv ]; then\n"
            "    python3 -m venv venv\n"
            "fi\n"
            "source venv/bin/activate\n"
            "pip install -q -r requirements.txt\n"
            "python main.py \"$@\"\n"
        )
        boot_bat = (
            "@echo off\n"
            "rem Argos OS — boot script (Windows)\n"
            "cd /d \"%~dp0\"\n"
            "if not exist venv python -m venv venv\n"
            "call venv\\Scripts\\activate.bat\n"
            "pip install -q -r requirements.txt\n"
            "python main.py %*\n"
        )

        import tempfile
        if not _PY7ZR_OK:
            return "❌ py7zr не установлен: pip install py7zr"
        try:
            file_count = 0
            with py7zr.SevenZipFile(image_path, mode="w") as zf:
                # Добавляем все файлы системы
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in exclude]
                    for file in files:
                        fp = os.path.join(root, file)
                        arcname = os.path.relpath(fp, ".")
                        try:
                            zf.write(fp, arcname)
                            file_count += 1
                            if file_count % 100 == 0:
                                log.debug("ArgosOS image: added %d files…", file_count)
                        except Exception as write_err:
                            log.warning("Failed to add %s to image: %s", fp, write_err)

                # Добавляем загрузочные скрипты
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".sh", delete=False, encoding="utf-8"
                ) as tmp_sh:
                    tmp_sh.write(boot_sh)
                    tmp_sh_path = tmp_sh.name

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".bat", delete=False, encoding="utf-8"
                ) as tmp_bat:
                    tmp_bat.write(boot_bat)
                    tmp_bat_path = tmp_bat.name

                try:
                    zf.write(tmp_sh_path, "start.sh")
                    zf.write(tmp_bat_path, "start.bat")
                finally:
                    os.unlink(tmp_sh_path)
                    os.unlink(tmp_bat_path)

            size_mb = os.path.getsize(image_path) / 1024 / 1024
            log.info("ArgosOS image created: %s (%.1f MB)", image_path, size_mb)
            return (
                f"✅ Образ Argos OS создан: {image_path} ({size_mb:.1f} MB)\n"
                f"   Для запуска: извлечь архив и выполнить start.sh (Linux/macOS) "
                f"или start.bat (Windows)."
            )
        except Exception as e:
            return f"❌ Ошибка создания образа Argos OS: {e}"

    def status(self) -> str:
        snaps = len(self.list_snapshots())
        replicas = 0
        images = 0
        try:
            replicas = len(os.listdir(self.replica_dir))
        except Exception:
            pass
        try:
            images = len(os.listdir(self.image_dir))
        except Exception:
            pass
        return (
            f"💾 REPLICATOR:\n"
            f"  Снимков:  {snaps}\n"
            f"  Реплик:   {replicas}\n"
            f"  Образов:  {images}\n"
            f"  Снимки:   {self.snapshot_dir}\n"
            f"  Реплики:  {self.replica_dir}"
        )
