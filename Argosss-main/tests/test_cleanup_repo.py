from pathlib import Path

from cleanup_repo import cleanup_repository


def test_cleanup_repository_removes_expected_artifacts(tmp_path: Path):
    project = tmp_path / "v1-3"
    project.mkdir()

    git_file = project / ".git" / "keep.txt"
    git_file.parent.mkdir(parents=True)
    git_file.write_text("keep")

    (project / "__pycache__" / "x.pyc").parent.mkdir(parents=True)
    (project / "__pycache__" / "x.pyc").write_bytes(b"1")

    (project / ".buildozer" / "cache.bin").parent.mkdir(parents=True)
    (project / ".buildozer" / "cache.bin").write_bytes(b"22")

    (project / "nested" / "999" / "dup.txt").parent.mkdir(parents=True)
    (project / "nested" / "999" / "dup.txt").write_bytes(b"333")

    (project / ".ipynb_checkpoints" / "cell.ipynb").parent.mkdir(parents=True)
    (project / ".ipynb_checkpoints" / "cell.ipynb").write_bytes(b"4444")

    (project / "run.log").write_bytes(b"55555")
    (project / "scratch.tmp").write_bytes(b"66")
    (project / "old.bak").write_bytes(b"77")
    (project / ".coverage").write_bytes(b"88")
    (project / "coverage.xml").write_bytes(b"99")
    (project / "mod.pyc").write_bytes(b"10")

    (project / "abc999" / "__init__.py").parent.mkdir(parents=True)
    (project / "abc999" / "__init__.py").write_bytes(b"11")

    result = cleanup_repository(project, input_func=lambda _: "n")

    assert git_file.exists()
    assert (project / ".buildozer").exists()
    assert not (project / "__pycache__").exists()
    assert not (project / "nested" / "999").exists()
    assert not (project / ".ipynb_checkpoints").exists()
    assert not (project / "run.log").exists()
    assert not (project / "scratch.tmp").exists()
    assert not (project / "old.bak").exists()
    assert not (project / ".coverage").exists()
    assert not (project / "coverage.xml").exists()
    assert not (project / "mod.pyc").exists()
    assert (project / "abc999" / "__init__.py").exists()
    assert (project / "abc999").exists()
    assert result.freed_bytes > 0


def test_cleanup_repository_removes_buildozer_when_confirmed(tmp_path: Path):
    project = tmp_path / "v1-3"
    project.mkdir()
    (project / ".buildozer" / "cache.bin").parent.mkdir(parents=True)
    (project / ".buildozer" / "cache.bin").write_bytes(b"1")

    result = cleanup_repository(project, input_func=lambda _: "y")

    assert not (project / ".buildozer").exists()
    assert any(".buildozer" in directory for directory in result.removed_dirs)
