#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_archive.py — Сборка релизного ZIP-архива ARGOS
=====================================================
Создаёт чистый архив исходного кода без бинарников,
баз данных, секретов и мусора.

Использование:
    python pack_archive.py                  # → releases/argos-v1.4.0.zip
    python pack_archive.py --version 1.4.0  # → releases/argos-v1.4.0.zip
    python pack_archive.py --output /tmp/my.zip
"""
from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path


# ── Директории, которые никогда не включаем ──────────────────────────────
EXCLUDE_DIRS: set[str] = {
    ".git", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".buildozer", "build", "builds",
    "dist", "bin", "data", "logs", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "releases",
}

# ── Расширения файлов, которые исключаем ────────────────────────────────
EXCLUDE_EXTENSIONS: set[str] = {
    ".pyc", ".pyo", ".pyd",
    ".db", ".sqlite", ".sqlite3",
    ".log", ".tmp", ".bak",
    ".pkg", ".pyz", ".toc",
    ".exe", ".dll", ".so", ".dylib",
    ".zip",                          # вложенные архивы
    ".docx", ".doc", ".xlsx", ".xls",
    ".coverage", ".coverage.*",
}

# ── Конкретные имена файлов, которые исключаем ──────────────────────────
EXCLUDE_FILES: set[str] = {
    ".env",                 # секреты
    "master.key",
    "node_id",
    "node_birth",
    "argos",                # Linux-бинарник
    "base_library.zip",
    "xref-argos.html",
}

# ── Файлы, которые включаем НЕСМОТРЯ на начало с точки ─────────────────
INCLUDE_DOTFILES: set[str] = {
    ".gitignore",
    ".env.example",
    ".vscode",
}


def _should_include(rel: Path) -> bool:
    """Возвращает True если файл нужно включить в архив."""
    parts = rel.parts

    # Исключить по директории
    for part in parts[:-1]:
        if part in EXCLUDE_DIRS:
            return False

    name = parts[-1]

    # Исключить скрытые файлы (кроме разрешённых)
    if name.startswith(".") and name not in INCLUDE_DOTFILES:
        return False

    # Исключить по имени
    if name in EXCLUDE_FILES:
        return False

    # Исключить по расширению
    suffix = Path(name).suffix.lower()
    if suffix in EXCLUDE_EXTENSIONS:
        return False

    return True


def build_archive(
    project_root: Path,
    output_path: Path,
    version: str = "1.3.0",
) -> tuple[int, int]:
    """
    Создаёт ZIP-архив релиза.

    Returns:
        (file_count, size_bytes) — количество файлов и размер архива.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    file_count = 0
    arc_prefix = f"argos-v{version}"   # корневая папка внутри ZIP

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for item in sorted(project_root.rglob("*")):
            if not item.is_file():
                continue
            rel = item.relative_to(project_root)
            if not _should_include(rel):
                continue
            arc_name = f"{arc_prefix}/{rel.as_posix()}"
            zf.write(item, arc_name)
            file_count += 1

    size_bytes = output_path.stat().st_size
    return file_count, size_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="ARGOS release archive builder")
    parser.add_argument("--version", default="1.4.0", help="Версия релиза (default: 1.4.0)")
    parser.add_argument("--output", default=None, help="Путь к выходному ZIP-файлу")
    parser.add_argument("--root", default=".", help="Корень проекта (default: .)")
    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    version = args.version

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = project_root / "releases" / f"argos-v{version}.zip"

    print(f"\n{'═' * 52}")
    print(f"  🔱 ARGOS Release Builder v{version}")
    print(f"{'═' * 52}")
    print(f"  Источник : {project_root}")
    print(f"  Архив    : {output_path}")
    print()

    file_count, size_bytes = build_archive(project_root, output_path, version)
    size_mb = size_bytes / (1024 * 1024)

    print(f"  ✅ Готово!")
    print(f"  Файлов   : {file_count}")
    print(f"  Размер   : {size_mb:.1f} МБ")
    print(f"{'═' * 52}\n")
    print(f"  Распаковать: unzip {output_path.name} -d argos")
    print(f"  Запустить:   cd argos-v{version} && launch.bat  (Windows)")
    print(f"               cd argos-v{version} && bash launch.sh  (Linux/Mac)")
    print(f"{'═' * 52}\n")


if __name__ == "__main__":
    main()
