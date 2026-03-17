"""Tests for src/admin.py — file operations: create, read, edit, append, rename, copy, delete."""
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.admin import ArgosAdmin


def make_admin():
    return ArgosAdmin()


# ── create_file ───────────────────────────────────────────────────────────────

def test_create_file_creates_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "hello.txt")
        admin = make_admin()
        result = admin.create_file(path, "Hello, Argos!")
        assert "✅" in result
        assert os.path.exists(path)
        with open(path) as f:
            assert f.read() == "Hello, Argos!"


def test_create_file_creates_subdirectory():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sub", "dir", "note.txt")
        admin = make_admin()
        result = admin.create_file(path, "nested")
        assert "✅" in result
        assert os.path.exists(path)


def test_create_file_empty_content():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "empty.txt")
        admin = make_admin()
        result = admin.create_file(path)
        assert "✅" in result
        assert os.path.getsize(path) == 0


# ── read_file ─────────────────────────────────────────────────────────────────

def test_read_file_returns_content():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Test content")
        path = f.name
    try:
        admin = make_admin()
        result = admin.read_file(path)
        assert "📄" in result
        assert "Test content" in result
        assert str(os.path.getsize(path)) in result  # shows size
    finally:
        os.unlink(path)


def test_read_file_missing():
    admin = make_admin()
    result = admin.read_file("/nonexistent/file_xyz_9999.txt")
    assert "Ошибка" in result


def test_read_file_binary():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(bytes(range(256)))
        path = f.name
    try:
        admin = make_admin()
        result = admin.read_file(path)
        assert "двоичный" in result or "байт" in result
    finally:
        os.unlink(path)


def test_read_file_truncation_note():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("A" * 3000)
        path = f.name
    try:
        admin = make_admin()
        result = admin.read_file(path)
        assert "3000" in result or "показано" in result
    finally:
        os.unlink(path)


# ── edit_file ─────────────────────────────────────────────────────────────────

def test_edit_file_replaces_text():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello World\nFoo Bar\n")
        path = f.name
    try:
        admin = make_admin()
        result = admin.edit_file(path, "World", "Argos")
        assert "✅" in result
        with open(path) as fh:
            assert "Argos" in fh.read()
            fh.seek(0)
            assert "World" not in fh.read()
    finally:
        os.unlink(path)


def test_edit_file_text_not_found():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello World\n")
        path = f.name
    try:
        admin = make_admin()
        result = admin.edit_file(path, "nonexistent_xyz", "replacement")
        assert "❌" in result
        assert "не найден" in result
    finally:
        os.unlink(path)


def test_edit_file_missing():
    admin = make_admin()
    result = admin.edit_file("/nonexistent/xyz.txt", "old", "new")
    assert "Ошибка" in result


def test_edit_file_only_first_occurrence():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("AAA AAA AAA\n")
        path = f.name
    try:
        admin = make_admin()
        admin.edit_file(path, "AAA", "BBB")
        with open(path) as fh:
            content = fh.read()
        assert content.count("BBB") == 1
        assert content.count("AAA") == 2
    finally:
        os.unlink(path)


# ── append_file ───────────────────────────────────────────────────────────────

def test_append_file_adds_content():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Line 1\n")
        path = f.name
    try:
        admin = make_admin()
        result = admin.append_file(path, "Line 2")
        assert "✅" in result
        with open(path) as fh:
            content = fh.read()
        assert "Line 1" in content
        assert "Line 2" in content
    finally:
        os.unlink(path)


def test_append_file_creates_if_missing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "new.txt")
        admin = make_admin()
        result = admin.append_file(path, "First line")
        assert "✅" in result
        assert os.path.exists(path)


# ── rename_file ───────────────────────────────────────────────────────────────

def test_rename_file_works():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "old.txt")
        dst = os.path.join(d, "new.txt")
        with open(src, "w") as f:
            f.write("data")
        admin = make_admin()
        result = admin.rename_file(src, dst)
        assert "✅" in result
        assert not os.path.exists(src)
        assert os.path.exists(dst)


def test_rename_file_missing_source():
    admin = make_admin()
    result = admin.rename_file("/nonexistent/src_xyz.txt", "/tmp/dst.txt")
    assert "❌" in result
    assert "не найден" in result.lower() or "Не найден" in result


# ── copy_file ─────────────────────────────────────────────────────────────────

def test_copy_file_works():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "orig.txt")
        dst = os.path.join(d, "copy.txt")
        with open(src, "w") as f:
            f.write("original content")
        admin = make_admin()
        result = admin.copy_file(src, dst)
        assert "✅" in result
        assert os.path.exists(src)
        assert os.path.exists(dst)
        with open(dst) as f:
            assert f.read() == "original content"


def test_copy_file_missing_source():
    admin = make_admin()
    result = admin.copy_file("/nonexistent/xyz.txt", "/tmp/dst.txt")
    assert "❌" in result


def test_copy_directory():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "srcdir")
        dst = os.path.join(d, "dstdir")
        os.makedirs(src)
        with open(os.path.join(src, "file.txt"), "w") as f:
            f.write("hello")
        admin = make_admin()
        result = admin.copy_file(src, dst)
        assert "✅" in result
        assert os.path.exists(os.path.join(dst, "file.txt"))


# ── delete_item ───────────────────────────────────────────────────────────────

def test_delete_file_works():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        path = f.name
    admin = make_admin()
    result = admin.delete_item(path)
    assert "🗑️" in result
    assert not os.path.exists(path)


def test_delete_directory_works():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "x.txt"), "w").close()
    admin = make_admin()
    result = admin.delete_item(d)
    assert "🗑️" in result
    assert not os.path.exists(d)


def test_delete_missing():
    admin = make_admin()
    result = admin.delete_item("/nonexistent_xyz_9999/path")
    assert "не найден" in result.lower() or "Объект" in result


# ── list_dir ──────────────────────────────────────────────────────────────────

def test_list_dir_works():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.txt"), "w").close()
        open(os.path.join(d, "b.txt"), "w").close()
        admin = make_admin()
        result = admin.list_dir(d)
        assert "📂" in result
        assert "a.txt" in result or "b.txt" in result


def test_list_dir_missing():
    admin = make_admin()
    result = admin.list_dir("/nonexistent_xyz_dir_9999")
    assert "Ошибка" in result
