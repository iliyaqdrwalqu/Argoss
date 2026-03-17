#!/usr/bin/env python3
"""
status_report.py — Полный отчёт о рабочем состоянии ARGOS.

Использование:
  python status_report.py              # вывод в консоль
  python status_report.py --json       # JSON-вывод (для CI/парсинга)
  python status_report.py --md         # Markdown (для GitHub Actions Summary)
  python status_report.py --out FILE   # сохранить отчёт в файл

Коды возврата:
  0 — всё в порядке (все обязательные компоненты зелёные)
  1 — есть критические проблемы (❌)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# ─── Тип статуса ─────────────────────────────────────────────────────────────
Status = Literal["ok", "warn", "error", "skip"]

ICON: dict[Status, str] = {
    "ok":    "✅",
    "warn":  "⚠️ ",
    "error": "❌",
    "skip":  "⏭️ ",
}

# ─── Структура одной проверки ─────────────────────────────────────────────────
@dataclass
class Check:
    name: str
    status: Status
    detail: str = ""

# ─── Группа проверок ──────────────────────────────────────────────────────────
@dataclass
class Section:
    title: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: Status, detail: str = "") -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def worst(self) -> Status:
        for s in ("error", "warn", "ok", "skip"):
            if any(c.status == s for c in self.checks):
                return s  # type: ignore[return-value]
        return "skip"

# ─── Вспомогательные функции ──────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.resolve()


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    """Выполнить команду, вернуть (returncode, combined_output)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(REPO_ROOT),
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, f"Команда не найдена: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "Тайм-аут"


def _pkg_version(name: str) -> str | None:
    """Вернуть версию установленного пакета или None."""
    try:
        import importlib.metadata
        return importlib.metadata.version(name)
    except Exception:
        return None


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _env(name: str) -> bool:
    """True если переменная окружения задана и не пустая."""
    return bool(os.environ.get(name, "").strip())

# ─── Сборщики секций ──────────────────────────────────────────────────────────

def check_environment() -> Section:
    s = Section("🖥️  Среда выполнения")

    # Python
    ver = sys.version_info
    py_ok = ver >= (3, 8)
    s.add("Python версия",
          "ok" if py_ok else "error",
          f"{sys.version.split()[0]} ({'достаточно' if py_ok else 'требуется ≥ 3.8'})")

    # ОС
    s.add("Операционная система", "ok", platform.platform())

    # Архитектура
    s.add("Архитектура", "ok", platform.machine())

    # Свободное место на диске (предупреждение < 500 МБ)
    try:
        usage = shutil.disk_usage(REPO_ROOT)
        free_mb = usage.free // (1024 * 1024)
        s.add("Свободное место",
              "ok" if free_mb >= 500 else "warn",
              f"{free_mb} МБ свободно")
    except Exception as e:
        s.add("Свободное место", "warn", str(e))

    return s


def check_git() -> Section:
    s = Section("📦 Git / репозиторий")

    # git доступен?
    code, out = _run(["git", "--version"])
    if code != 0:
        s.add("git", "error", "git не найден")
        return s
    s.add("git", "ok", out.strip())

    # Текущая ветка
    _, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    s.add("Текущая ветка", "ok", branch)

    # Последний коммит
    _, commit = _run(["git", "log", "-1", "--format=%h %s %ai"])
    s.add("Последний коммит", "ok", commit)

    # Статус рабочего дерева
    _, wt = _run(["git", "status", "--porcelain"])
    if wt:
        s.add("Рабочее дерево", "warn", f"Незакоммиченные изменения:\n{wt}")
    else:
        s.add("Рабочее дерево", "ok", "Чисто (нет изменений)")

    # Remote origin
    _, origin = _run(["git", "remote", "get-url", "origin"])
    s.add("Remote origin", "ok" if origin else "warn", origin or "не задан")

    return s


def check_core_files() -> Section:
    s = Section("📁 Ключевые файлы проекта")

    required = {
        "main.py": "Основной модуль (GUI / web / terminal)",
        "requirements.txt": "Зависимости Python",
        "buildozer.spec": "Конфигурация сборки APK",
        "telegram_bot.py": "Telegram-бот с историей чата",
        "argos_model.py": "Локальная нейросеть Аргоса",
        "git_push.py": "Скрипт автопуша коммитов",
        "README.md": "Документация",
        ".github/workflows/build_apk.yml": "CI сборка APK",
        ".github/workflows/auto_push.yml": "CI автопуш",
        ".github/workflows/status_report.yml": "CI отчёт о состоянии",
    }

    for rel_path, description in required.items():
        full = REPO_ROOT / rel_path
        if full.exists():
            size = full.stat().st_size
            s.add(rel_path, "ok", f"{description} ({size} байт)")
        else:
            # Workflow отчёта ещё может не существовать — не критично
            status: Status = "warn" if rel_path.endswith("status_report.yml") else "error"
            s.add(rel_path, status, f"ОТСУТСТВУЕТ — {description}")

    return s


def check_python_dependencies() -> Section:
    s = Section("📦 Python-зависимости")

    packages = {
        # Пакет PyPI: (минимальная версия, обязателен?)
        "aiogram":        ("3.0.0", True),
        "aiosqlite":      ("0.17.0", True),
        "python-dotenv":  ("0.19.0", True),
        "openai":         ("1.0.0", True),
        "fastapi":        ("0.100.0", False),
        "uvicorn":        ("0.20.0", False),
        "kivy":           ("2.0.0", False),
        "buildozer":      ("1.5.0", False),
        "scikit-learn":   ("1.0.0", False),
        "numpy":          ("1.21.0", False),
    }

    # Маппинг "pip-имя" → "import-имя" для тех, где они различаются
    import_name_map = {
        "python-dotenv": "dotenv",
        "scikit-learn":  "sklearn",
    }

    for pkg, (min_ver, required) in packages.items():
        ver = _pkg_version(pkg)
        imp = import_name_map.get(pkg, pkg.replace("-", "_"))
        importable = _has_module(imp)

        if ver:
            s.add(pkg, "ok", f"v{ver} ({'обязателен' if required else 'опционально'})")
        elif importable:
            s.add(pkg, "warn", "Установлен, но версия не определена")
        elif required:
            s.add(pkg, "warn", "Не установлен (выполните: pip install -r requirements.txt)")
        else:
            s.add(pkg, "skip", "Не установлен (опционально)")

    return s


def check_env_vars() -> Section:
    s = Section("🔑 Переменные окружения")

    vars_info = {
        "TELEGRAM_TOKEN": ("Токен Telegram-бота", True),
        "OPENAI_API_KEY":  ("API-ключ OpenAI (GPT)", True),
        "GIT_TOKEN":       ("Personal Access Token для git push", False),
        "GIT_USER":        ("git user.name (автопуш)", False),
        "GIT_EMAIL":       ("git user.email (автопуш)", False),
    }

    for var, (description, required) in vars_info.items():
        present = _env(var)
        if present:
            s.add(var, "ok", f"{description} — задан ✓")
        elif required:
            s.add(var, "warn", f"{description} — НЕ ЗАДАН (бот не запустится)")
        else:
            s.add(var, "skip", f"{description} — не задан (опционально)")

    return s


def check_system_tools() -> Section:
    s = Section("🛠️  Системные инструменты")

    tools = {
        "git":      (["git", "--version"], True),
        "python3":  ([sys.executable, "--version"], True),
        "pip":      (["pip", "--version"], True),
        "java":     (["java", "-version"], False),
        "adb":      (["adb", "version"], False),
        "buildozer": (["buildozer", "--version"], False),
    }

    for tool, (cmd, required) in tools.items():
        code, out = _run(cmd)
        if code == 0:
            ver_line = out.splitlines()[0] if out else "OK"
            s.add(tool, "ok", ver_line)
        elif code == 127:
            s.add(tool, "error" if required else "skip",
                  "Не найден" + (" (обязателен)" if required else " (опционально)"))
        else:
            s.add(tool, "warn", f"Код возврата {code}: {out[:80]}")

    return s


def check_argos_runtime() -> Section:
    s = Section("🔱 ARGOS Runtime")

    main_path = REPO_ROOT / "main.py"

    # Читаем main.py и проверяем на наличие Jupyter-магии (%%writefile ...)
    try:
        raw = main_path.read_text(encoding="utf-8")
    except Exception as e:
        s.add("main.py чтение", "error", str(e))
        return s

    first_line = raw.splitlines()[0] if raw else ""
    if first_line.startswith("%%"):
        s.add(
            "main.py Jupyter-магия",
            "warn",
            f"Первая строка — Colab-директива: '{first_line}'. "
            "Удалите её для корректного выполнения вне Colab.",
        )
        # Убираем магическую строку, чтобы попробовать выполнить остаток
        clean_src = "\n".join(raw.splitlines()[1:])
    else:
        s.add("main.py Jupyter-магия", "ok", "Магических директив не найдено")
        clean_src = raw

    # Синтаксическая проверка очищенного кода
    import py_compile, tempfile, io as _io
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         delete=False, encoding="utf-8") as tf:
            tf.write(clean_src)
            tf_name = tf.name
        py_compile.compile(tf_name, doraise=True)
        s.add("main.py синтаксис", "ok", "OK")
    except py_compile.PyCompileError as e:
        s.add("main.py синтаксис", "error", str(e))
        return s
    finally:
        Path(tf_name).unlink(missing_ok=True)

    # Импортируем ArgosAbsolute из очищенного main.py
    try:
        import importlib.util as ilu
        import types, tempfile as _tf, os as _os

        with _tf.NamedTemporaryFile(mode="w", suffix=".py",
                                     delete=False, encoding="utf-8") as tf2:
            tf2.write(clean_src)
            tf2_name = tf2.name

        os.environ.setdefault("KIVY_NO_ARGS", "1")
        spec = ilu.spec_from_file_location("_argos_main", tf2_name)
        captured = _io.StringIO()
        sys.stderr = captured
        try:
            mod = ilu.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        finally:
            sys.stderr = sys.__stderr__
            Path(tf2_name).unlink(missing_ok=True)

        core = mod.ArgosAbsolute()
        s.add("ArgosAbsolute инициализация", "ok",
              f"node_id={core.node_id}, version={core.version}")

        # Тест команд
        for cmd, expected in [("nfc", "NFC"), ("bt", "BT"), ("root", "ROOT")]:
            result = core.execute(cmd)
            ok = expected in result
            s.add(f"execute('{cmd}')", "ok" if ok else "warn", result[:80])

    except Exception as e:
        s.add("ArgosAbsolute", "error", str(e))

    # Telegram bot — просто проверяем синтаксис
    try:
        import py_compile
        py_compile.compile(str(REPO_ROOT / "telegram_bot.py"), doraise=True)
        s.add("telegram_bot.py синтаксис", "ok", "OK")
    except Exception as e:
        s.add("telegram_bot.py синтаксис", "error", str(e))

    # buildozer.spec существует и не пустой
    spec_path = REPO_ROOT / "buildozer.spec"
    if spec_path.exists() and spec_path.stat().st_size > 100:
        s.add("buildozer.spec", "ok", f"{spec_path.stat().st_size} байт")
    else:
        s.add("buildozer.spec", "warn", "Отсутствует или пустой")

    return s


def check_github_actions() -> Section:
    s = Section("⚙️  GitHub Actions / CI")

    workflows_dir = REPO_ROOT / ".github" / "workflows"
    if not workflows_dir.exists():
        s.add("Директория workflows", "error", "Не найдена")
        return s

    s.add("Директория workflows", "ok", str(workflows_dir))

    expected_workflows = {
        "build_apk.yml": "Сборка Android APK",
        "auto_push.yml": "Автоматический пуш коммитов",
        "status_report.yml": "Отчёт о рабочем состоянии",
    }

    for wf, description in expected_workflows.items():
        path = workflows_dir / wf
        if path.exists():
            s.add(wf, "ok", f"{description} ({path.stat().st_size} байт)")
        else:
            s.add(wf, "warn", f"ОТСУТСТВУЕТ — {description}")

    # Синтаксис YAML (базовая проверка)
    try:
        import yaml  # type: ignore[import]
        has_yaml = True
    except ImportError:
        has_yaml = False

    if has_yaml:
        for wf_file in workflows_dir.glob("*.yml"):
            try:
                with open(wf_file) as f:
                    yaml.safe_load(f)
                s.add(f"{wf_file.name} YAML", "ok", "Синтаксис корректен")
            except Exception as e:
                s.add(f"{wf_file.name} YAML", "error", str(e))
    else:
        s.add("YAML-валидация", "skip", "PyYAML не установлен (pip install pyyaml)")

    return s

# ─── Генерация отчёта ─────────────────────────────────────────────────────────

def collect_report() -> list[Section]:
    collectors = [
        check_environment,
        check_git,
        check_core_files,
        check_python_dependencies,
        check_env_vars,
        check_system_tools,
        check_argos_runtime,
        check_github_actions,
    ]
    return [fn() for fn in collectors]


def format_console(sections: list[Section], ts: str) -> str:
    lines = [
        "═" * 70,
        f"  🔱 ARGOS — ПОЛНЫЙ ОТЧЁТ О РАБОЧЕМ СОСТОЯНИИ",
        f"  Сгенерирован: {ts}",
        "═" * 70,
    ]
    for sec in sections:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"  {sec.title}")
        lines.append("─" * 70)
        for chk in sec.checks:
            icon = ICON[chk.status]
            detail = f"  →  {chk.detail}" if chk.detail else ""
            lines.append(f"  {icon} {chk.name}{detail}")

    # Сводка
    all_checks = [c for sec in sections for c in sec.checks]
    n_ok    = sum(1 for c in all_checks if c.status == "ok")
    n_warn  = sum(1 for c in all_checks if c.status == "warn")
    n_err   = sum(1 for c in all_checks if c.status == "error")
    n_skip  = sum(1 for c in all_checks if c.status == "skip")

    lines += [
        "",
        "═" * 70,
        "  📊 ИТОГО",
        "═" * 70,
        f"  ✅ OK:           {n_ok}",
        f"  ⚠️  ПРЕДУПРЕЖДЕНИЙ: {n_warn}",
        f"  ❌ ОШИБОК:       {n_err}",
        f"  ⏭️  ПРОПУЩЕНО:    {n_skip}",
        "",
        f"  Общий статус: {'✅ РАБОТОСПОСОБЕН' if n_err == 0 else '❌ ЕСТЬ КРИТИЧЕСКИЕ ПРОБЛЕМЫ'}",
        "═" * 70,
    ]
    return "\n".join(lines)


def format_markdown(sections: list[Section], ts: str) -> str:
    lines = [
        "# 🔱 ARGOS — Полный отчёт о рабочем состоянии",
        f"> Сгенерирован: `{ts}`",
        "",
    ]
    for sec in sections:
        lines.append(f"## {sec.title}")
        lines.append("")
        lines.append("| Статус | Проверка | Подробности |")
        lines.append("|--------|----------|-------------|")
        for chk in sec.checks:
            icon = ICON[chk.status]
            detail = chk.detail.replace("\n", "<br>")
            lines.append(f"| {icon} | {chk.name} | {detail} |")
        lines.append("")

    all_checks = [c for sec in sections for c in sec.checks]
    n_ok    = sum(1 for c in all_checks if c.status == "ok")
    n_warn  = sum(1 for c in all_checks if c.status == "warn")
    n_err   = sum(1 for c in all_checks if c.status == "error")
    n_skip  = sum(1 for c in all_checks if c.status == "skip")

    overall = "✅ **РАБОТОСПОСОБЕН**" if n_err == 0 else "❌ **ЕСТЬ КРИТИЧЕСКИЕ ПРОБЛЕМЫ**"
    lines += [
        "---",
        "## 📊 Итого",
        "",
        f"| ✅ OK | ⚠️  Предупреждений | ❌ Ошибок | ⏭️  Пропущено |",
        f"|-------|------------------|----------|------------|",
        f"| {n_ok} | {n_warn} | {n_err} | {n_skip} |",
        "",
        f"**Общий статус:** {overall}",
    ]
    return "\n".join(lines)


def format_json(sections: list[Section], ts: str) -> str:
    data = {
        "generated_at": ts,
        "sections": [
            {
                "title": sec.title,
                "worst_status": sec.worst,
                "checks": [asdict(c) for c in sec.checks],
            }
            for sec in sections
        ],
    }
    all_checks = [c for sec in sections for c in sec.checks]
    data["summary"] = {
        "ok":    sum(1 for c in all_checks if c.status == "ok"),
        "warn":  sum(1 for c in all_checks if c.status == "warn"),
        "error": sum(1 for c in all_checks if c.status == "error"),
        "skip":  sum(1 for c in all_checks if c.status == "skip"),
        "overall": "ok" if not any(c.status == "error" for c in all_checks) else "error",
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


# ─── Точка входа ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Полный отчёт о рабочем состоянии ARGOS",
    )
    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument("--json", action="store_true", help="Вывод в JSON")
    fmt_group.add_argument("--md",   action="store_true", help="Вывод в Markdown")
    parser.add_argument("--out", metavar="FILE", help="Сохранить отчёт в файл")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sections = collect_report()

    if args.json:
        text = format_json(sections, ts)
    elif args.md:
        text = format_markdown(sections, ts)
    else:
        text = format_console(sections, ts)

    print(text)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\n📝 Отчёт сохранён: {args.out}", file=sys.stderr)

    # Код возврата: 1 если есть ❌ ошибки
    all_checks = [c for sec in sections for c in sec.checks]
    has_errors = any(c.status == "error" for c in all_checks)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
