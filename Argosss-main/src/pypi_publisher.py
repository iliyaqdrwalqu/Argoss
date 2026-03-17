"""
pypi_publisher.py — Публикация навыков Аргоса на PyPI
  Автоматически упаковывает навык в Python-пакет и публикует на PyPI.
  Также поддерживает автоматический bump версии и git-тег.

  Требования:
    pip install twine build

  Переменные окружения (.env):
    PYPI_TOKEN=pypi-xxxxxxxxxxxx        # токен PyPI (Settings → API tokens)
    PYPI_TEST=1                         # публиковать на test.pypi.org (опционально)

  Команды Аргоса:
    pypi статус
    pypi опубликовать [skill_name]
    pypi список
    pypi версия [skill_name] [version]
    pypi собрать [skill_name]
"""

from __future__ import annotations

import os
import re
import sys
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from src.argos_logger import get_logger

log = get_logger("argos.pypi")

SKILLS_DIR = Path("src/skills")
PYPI_HISTORY = Path("data/pypi_publish_history.jsonl")


class ArgosPyPIPublisher:
    """
    Упаковывает и публикует навыки Аргоса как Python-пакеты на PyPI.
    Каждый навык становится отдельным pip-устанавливаемым пакетом:
      pip install argos-skill-crypto-monitor
    """

    def __init__(self, core=None):
        self.core = core
        self.token = os.getenv("PYPI_TOKEN", "").strip()
        self.use_test = os.getenv("PYPI_TEST", "0").strip() in {"1", "true", "yes"}
        self.author = os.getenv("PYPI_AUTHOR", "Vsevolod / ARGOS").strip()
        self.author_email = os.getenv("PYPI_AUTHOR_EMAIL", "argos@sigtrip.dev").strip()
        self.repo_url = os.getenv("GITHUB_REPO_URL", "https://github.com/sigtrip/v1-3").strip()

    # ── ПРОВЕРКИ ──────────────────────────────────────────

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _check_tools(self) -> tuple[bool, str]:
        missing = []
        for tool in ["build", "twine"]:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", tool, "--version"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0:
                    missing.append(tool)
            except Exception:
                missing.append(tool)
        if missing:
            return False, f"Установи: pip install {' '.join(missing)}"
        return True, "ok"

    def status(self) -> str:
        tools_ok, tools_msg = self._check_tools()
        registry = "test.pypi.org" if self.use_test else "pypi.org"
        return (
            f"📦 ARGOS PyPI Publisher:\n"
            f"  Токен:    {'✅ установлен' if self.configured else '❌ нет (PYPI_TOKEN в .env)'}\n"
            f"  Registry: {registry}\n"
            f"  Инструменты: {'✅ ok' if tools_ok else f'❌ {tools_msg}'}\n"
            f"  Автор:    {self.author}\n"
            f"  Навыки в src/skills/: {len(list(SKILLS_DIR.glob('*.py')))}"
        )

    # ── ФОРМИРОВАНИЕ ПАКЕТА ───────────────────────────────

    def _skill_to_package_name(self, skill_name: str) -> str:
        """Преобразует имя навыка в имя PyPI-пакета."""
        clean = re.sub(r"[^a-z0-9]+", "-", skill_name.lower().strip())
        return f"argos-skill-{clean.strip('-')}"

    def _read_skill_version(self, skill_name: str) -> str:
        """Читает версию из навыка или генерирует дату-версию."""
        skill_file = SKILLS_DIR / f"{skill_name}.py"
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if m:
                return m.group(1)
            m = re.search(r'version\s*[=:]\s*["\']([^"\']+)["\']', content)
            if m:
                return m.group(1)
        # Версия по дате: 2026.3.11
        now = datetime.now()
        return f"{now.year}.{now.month}.{now.day}"

    def _build_package(self, skill_name: str, version: str, build_dir: Path) -> tuple[bool, str]:
        """Создаёт структуру пакета и собирает wheel + sdist."""
        pkg_name = self._skill_to_package_name(skill_name)
        pkg_name_py = pkg_name.replace("-", "_")

        skill_file = SKILLS_DIR / f"{skill_name}.py"
        if not skill_file.exists():
            return False, f"Навык не найден: {skill_file}"

        skill_code = skill_file.read_text(encoding="utf-8")

        # Создаём структуру пакета во временной папке
        pkg_dir = build_dir / pkg_name_py
        pkg_dir.mkdir(parents=True)

        # __init__.py
        (pkg_dir / "__init__.py").write_text(
            f'"""ARGOS Skill: {skill_name}\nАвтоматически опубликовано системой Аргос."""\n'
            f"__version__ = \"{version}\"\n"
            f"from .skill import *\n",
            encoding="utf-8"
        )

        # skill.py — основной код навыка
        (pkg_dir / "skill.py").write_text(skill_code, encoding="utf-8")

        # README.md
        readme = (
            f"# {pkg_name}\n\n"
            f"> Навык для ARGOS Universal OS. Автоматически опубликован системой эволюции.\n\n"
            f"## Установка\n\n"
            f"```bash\npip install {pkg_name}\n```\n\n"
            f"## Использование\n\n"
            f"```python\nfrom {pkg_name_py}.skill import *\n```\n\n"
            f"## Репозиторий\n\n"
            f"{self.repo_url}\n\n"
            f"---\n*Опубликовано ARGOS v1.3 · {datetime.now().strftime('%Y-%m-%d')}*\n"
        )
        (build_dir / "README.md").write_text(readme, encoding="utf-8")

        # pyproject.toml (современный стандарт)
        pyproject = f"""[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "{pkg_name}"
version = "{version}"
description = "ARGOS Skill: {skill_name} — автономный навык ИИ-системы Аргос"
readme = "README.md"
license = {{text = "Apache-2.0"}}
authors = [{{name = "{self.author}", email = "{self.author_email}"}}]
requires-python = ">=3.10"
keywords = ["argos", "ai", "skill", "autonomous", "{skill_name}"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]

[project.urls]
Homepage = "{self.repo_url}"
Repository = "{self.repo_url}"

[tool.setuptools.packages.find]
where = ["."]
include = ["{pkg_name_py}*"]
"""
        (build_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")

        # Сборка wheel + sdist
        log.info("Собираю пакет %s v%s...", pkg_name, version)
        result = subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(build_dir / "dist")],
            cwd=str(build_dir),
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            return False, f"Ошибка сборки:\n{result.stderr[-800:]}"

        dist_files = list((build_dir / "dist").glob("*"))
        if not dist_files:
            return False, "Дистрибутивы не созданы."

        log.info("Пакет собран: %s", [f.name for f in dist_files])
        return True, str(build_dir / "dist")

    # ── ПУБЛИКАЦИЯ ────────────────────────────────────────

    def publish(self, skill_name: str, version: str = None) -> str:
        """Собирает и публикует навык на PyPI."""
        if not self.configured:
            return (
                "❌ PYPI_TOKEN не установлен.\n"
                "  1. Зайди на pypi.org → Account Settings → API tokens\n"
                "  2. Создай токен с scope: Entire account или конкретный проект\n"
                "  3. Добавь в .env: PYPI_TOKEN=pypi-xxxxxxxxxxxx"
            )

        tools_ok, tools_msg = self._check_tools()
        if not tools_ok:
            return f"❌ {tools_msg}"

        skill_file = SKILLS_DIR / f"{skill_name}.py"
        if not skill_file.exists():
            available = [f.stem for f in SKILLS_DIR.glob("*.py") if not f.stem.startswith("__")]
            return (
                f"❌ Навык '{skill_name}' не найден.\n"
                f"Доступные навыки: {', '.join(available[:15])}"
            )

        ver = version or self._read_skill_version(skill_name)
        pkg_name = self._skill_to_package_name(skill_name)
        registry_url = (
            "https://test.pypi.org/legacy/" if self.use_test
            else "https://upload.pypi.org/legacy/"
        )
        registry_name = "TestPyPI" if self.use_test else "PyPI"

        log.info("Публикую навык '%s' v%s на %s...", skill_name, ver, registry_name)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Сборка
            build_ok, build_result = self._build_package(skill_name, ver, tmp_path)
            if not build_ok:
                return f"❌ Сборка не удалась:\n{build_result}"

            dist_dir = build_result
            dist_files = list(Path(dist_dir).glob("*"))

            # Публикация через twine
            upload_cmd = [
                sys.executable, "-m", "twine", "upload",
                "--repository-url", registry_url,
                "--username", "__token__",
                "--password", self.token,
                "--non-interactive",
            ] + [str(f) for f in dist_files]

            upload_result = subprocess.run(
                upload_cmd, capture_output=True, text=True, timeout=120
            )

            if upload_result.returncode != 0:
                err = upload_result.stderr or upload_result.stdout
                # Обработка "уже существует"
                if "already exists" in err or "File already exists" in err:
                    return (
                        f"⚠️ Версия {ver} уже опубликована.\n"
                        f"Используй: pypi версия {skill_name} {self._bump_version(ver)}"
                    )
                return f"❌ Ошибка публикации:\n{err[-600:]}"

            # Логируем успех
            entry = {
                "skill": skill_name,
                "package": pkg_name,
                "version": ver,
                "registry": registry_name,
                "published_at": datetime.now().isoformat(),
            }
            PYPI_HISTORY.parent.mkdir(parents=True, exist_ok=True)
            with open(PYPI_HISTORY, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            pip_cmd = f"pip install {pkg_name}"
            if self.use_test:
                pip_cmd = f"pip install --index-url https://test.pypi.org/simple/ {pkg_name}"

            return (
                f"🚀 НАВЫК ОПУБЛИКОВАН НА {registry_name}!\n"
                f"  Пакет:   {pkg_name}\n"
                f"  Версия:  {ver}\n"
                f"  Установка: {pip_cmd}\n"
                f"  URL: https://{'test.' if self.use_test else ''}pypi.org/project/{pkg_name}/"
            )

    def _bump_version(self, version: str) -> str:
        """Увеличивает patch-версию: 1.2.3 → 1.2.4"""
        parts = version.split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except ValueError:
            parts.append("1")
        return ".".join(parts)

    # ── СПИСОК ОПУБЛИКОВАННЫХ ─────────────────────────────

    def list_published(self) -> str:
        if not PYPI_HISTORY.exists():
            return "📦 Ещё ни один навык не опубликован на PyPI."
        lines = ["📦 ОПУБЛИКОВАННЫЕ НАВЫКИ:"]
        try:
            with open(PYPI_HISTORY, "r", encoding="utf-8") as f:
                entries = [json.loads(l) for l in f.readlines()]
            # Последняя версия каждого пакета
            latest = {}
            for e in entries:
                latest[e["skill"]] = e
            for skill, e in sorted(latest.items()):
                lines.append(
                    f"  • {e['package']} v{e['version']} "
                    f"[{e['registry']}] {e['published_at'][:10]}"
                )
        except Exception as ex:
            return f"❌ Ошибка: {ex}"
        return "\n".join(lines)

    def build_only(self, skill_name: str) -> str:
        """Только собирает пакет без публикации."""
        skill_file = SKILLS_DIR / f"{skill_name}.py"
        if not skill_file.exists():
            return f"❌ Навык не найден: {skill_name}"
        ver = self._read_skill_version(skill_name)
        out_dir = Path("dist/skills")
        out_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            ok, result = self._build_package(skill_name, ver, Path(tmp))
            if not ok:
                return f"❌ {result}"
            # Копируем в dist/skills/
            for f in Path(result).glob("*"):
                shutil.copy(f, out_dir / f.name)

        files = list(out_dir.glob(f"*{skill_name.replace('_','-')}*"))
        return (
            f"📦 Пакет собран в dist/skills/:\n"
            + "\n".join(f"  • {f.name}" for f in files)
        )
