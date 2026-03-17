from pathlib import Path

from organize_files import organize_files


def _write(path: Path, data: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_organize_files_moves_expected_files(tmp_path: Path):
    _write(tmp_path / "main.py")
    _write(tmp_path / "README.md")
    _write(tmp_path / ".env")
    _write(tmp_path / "CHANGELOG.md")
    _write(tmp_path / "build_exe.py")
    _write(tmp_path / "Dockerfile.windows")
    _write(tmp_path / "random.ipynb")
    _write(tmp_path / "notes.txt")
    _write(tmp_path / "quickstart.md")
    _write(tmp_path / "docs" / "CONTRIBUTING.md")
    _write(tmp_path / "CONTRIBUTING.md")

    result = organize_files(tmp_path)

    assert (tmp_path / "main.py").exists()
    assert (tmp_path / "README.md").exists()
    assert (tmp_path / ".env").exists()

    assert not (tmp_path / "CHANGELOG.md").exists()
    assert (tmp_path / "docs" / "CHANGELOG.md").exists()
    assert not (tmp_path / "build_exe.py").exists()
    assert (tmp_path / "scripts" / "build_exe.py").exists()
    assert not (tmp_path / "Dockerfile.windows").exists()
    assert (tmp_path / "docker" / "Dockerfile.windows").exists()
    assert not (tmp_path / "random.ipynb").exists()
    assert (tmp_path / "notebooks" / "random.ipynb").exists()
    assert not (tmp_path / "notes.txt").exists()
    assert (tmp_path / "reports" / "notes.txt").exists()
    assert not (tmp_path / "quickstart.md").exists()
    assert (tmp_path / "docs" / "quickstart.md").exists()
    assert (tmp_path / "CONTRIBUTING.md").exists()
    assert (tmp_path / "docs" / "CONTRIBUTING.md").exists()
    assert len(result.moved) == 6


def test_organize_files_keeps_nested_files_untouched(tmp_path: Path):
    _write(tmp_path / "nested" / "keep.md")
    _write(tmp_path / "nested" / "keep.txt")
    _write(tmp_path / "nested" / "keep.ipynb")

    organize_files(tmp_path)

    assert (tmp_path / "nested" / "keep.md").exists()
    assert (tmp_path / "nested" / "keep.txt").exists()
    assert (tmp_path / "nested" / "keep.ipynb").exists()
