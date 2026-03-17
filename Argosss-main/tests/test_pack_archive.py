"""tests/test_pack_archive.py — Проверка сборщика релизного архива."""
from __future__ import annotations

import zipfile
from pathlib import Path

from pack_archive import _should_include, build_archive


# ── _should_include ──────────────────────────────────────────────────────

def test_includes_main_py():
    assert _should_include(Path("main.py")) is True

def test_includes_src_file():
    assert _should_include(Path("src/core.py")) is True

def test_includes_launch_bat():
    assert _should_include(Path("launch.bat")) is True

def test_includes_launch_ps1():
    assert _should_include(Path("launch.ps1")) is True

def test_includes_gitignore():
    assert _should_include(Path(".gitignore")) is True

def test_excludes_pyc():
    assert _should_include(Path("src/core.cpython-312.pyc")) is False

def test_excludes_db():
    assert _should_include(Path("argos.db")) is False

def test_excludes_log():
    assert _should_include(Path("argos.log")) is False

def test_excludes_env_secret():
    assert _should_include(Path(".env")) is False

def test_excludes_master_key():
    assert _should_include(Path("master.key")) is False

def test_excludes_pyz():
    assert _should_include(Path("PYZ-00.pyz")) is False

def test_excludes_exe():
    assert _should_include(Path("setup_argos.exe")) is False

def test_excludes_toc():
    assert _should_include(Path("Analysis-00.toc")) is False

def test_excludes_docx():
    assert _should_include(Path("argos_arch.docx")) is False

def test_excludes_git_dir():
    assert _should_include(Path(".git/config")) is False

def test_excludes_pycache_dir():
    assert _should_include(Path("src/__pycache__/core.cpython-312.pyc")) is False

def test_excludes_nested_zip():
    assert _should_include(Path("v1-3-1.3.0.zip")) is False

def test_excludes_data_dir():
    assert _should_include(Path("data/argos.db")) is False


# ── build_archive ────────────────────────────────────────────────────────

def test_build_archive_creates_zip(tmp_path: Path):
    """build_archive создаёт непустой корректный ZIP с нужными файлами."""
    # Создаём минимальную структуру проекта
    (tmp_path / "main.py").write_text("# main", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (tmp_path / "launch.bat").write_text("@echo off\r\n", encoding="utf-8")
    (tmp_path / "launch.ps1").write_text("# ps1\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "core.py").write_text("# core", encoding="utf-8")

    # Файлы, которые должны быть исключены
    (tmp_path / ".env").write_text("SECRET=123", encoding="utf-8")
    (tmp_path / "argos.db").write_bytes(b"\x00" * 16)
    (tmp_path / "setup_argos.exe").write_bytes(b"\x00" * 16)

    out = tmp_path / "releases" / "argos-v1.3.0.zip"
    count, size = build_archive(tmp_path, out, "1.3.0")

    assert out.exists(), "ZIP не создан"
    assert count >= 4, f"Мало файлов в архиве: {count}"
    assert size > 0

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()

    assert any("main.py" in n for n in names)
    assert any("launch.bat" in n for n in names)
    assert any("launch.ps1" in n for n in names)
    assert any("src/core.py" in n for n in names)
    assert not any(".env" in n for n in names), ".env не должен попасть в архив"
    assert not any(".db" in n for n in names), ".db не должен попасть в архив"
    assert not any(".exe" in n for n in names), ".exe не должен попасть в архив"


def test_build_archive_uses_version_prefix(tmp_path: Path):
    """Все записи в ZIP начинаются с argos-vX.Y.Z/"""
    (tmp_path / "main.py").write_text("# main", encoding="utf-8")
    out = tmp_path / "out.zip"
    build_archive(tmp_path, out, "9.9.9")

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()

    assert all(n.startswith("argos-v9.9.9/") for n in names), \
        f"Найдены записи без prefix: {[n for n in names if not n.startswith('argos-v9.9.9/')]}"
