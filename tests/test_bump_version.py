"""tests/test_bump_version.py — unit tests for bump_version.py"""
import re
import sys
from pathlib import Path

import pytest

# bump_version.py lives in the project root, not in a package
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bump_version import bump, OLD, NEW, TARGETS, REMOVE, RENAME


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_old_version_format(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", OLD)

    def test_new_version_format(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", NEW)

    def test_targets_is_list_of_triples(self):
        for item in TARGETS:
            assert len(item) == 3, f"TARGETS entry should be a 3-tuple, got {item!r}"

    def test_remove_is_list_of_strings(self):
        for item in REMOVE:
            assert isinstance(item, str)

    def test_rename_is_list_of_pairs(self):
        for item in RENAME:
            assert len(item) == 2, f"RENAME entry should be a 2-tuple, got {item!r}"


# ---------------------------------------------------------------------------
# bump() — dry_run does not write files
# ---------------------------------------------------------------------------

class TestBumpDryRun:
    def test_dry_run_does_not_modify_files(self, tmp_path, monkeypatch):
        """bump(dry_run=True) must not write any file."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(f'version = "{OLD}"\n', encoding="utf-8")

        # Patch __file__ equivalent: make bump() resolve root to tmp_path
        import bump_version as bv
        monkeypatch.setattr(bv, "__file__", str(tmp_path / "bump_version.py"))

        bump(dry_run=True)

        content_after = pyproject.read_text(encoding="utf-8")
        assert OLD in content_after, "dry_run must NOT modify pyproject.toml"

    def test_dry_run_returns_none(self, tmp_path, monkeypatch):
        import bump_version as bv
        monkeypatch.setattr(bv, "__file__", str(tmp_path / "bump_version.py"))
        result = bump(dry_run=True)
        assert result is None  # function returns nothing


# ---------------------------------------------------------------------------
# bump() — actually bumps versions in temp files
# ---------------------------------------------------------------------------

class TestBumpActual:
    def _setup_files(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            f'[tool.poetry]\nversion = "{OLD}"\n', encoding="utf-8"
        )
        (tmp_path / "README.md").write_text(
            f"# ARGOS UNIVERSAL OS (v{OLD})\n[{OLD}] changelog\n", encoding="utf-8"
        )
        (tmp_path / "manifest.json").write_text(
            f'{{"version": "{OLD}"}}\n', encoding="utf-8"
        )
        (tmp_path / "manifest.yaml").write_text(
            f"version: {OLD}\n", encoding="utf-8"
        )

    def test_pyproject_version_bumped(self, tmp_path, monkeypatch):
        self._setup_files(tmp_path)
        import bump_version as bv
        monkeypatch.setattr(bv, "__file__", str(tmp_path / "bump_version.py"))
        bump(dry_run=False)
        content = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
        assert NEW in content
        assert OLD not in content

    def test_readme_version_bumped(self, tmp_path, monkeypatch):
        self._setup_files(tmp_path)
        import bump_version as bv
        monkeypatch.setattr(bv, "__file__", str(tmp_path / "bump_version.py"))
        bump(dry_run=False)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert NEW in content

    def test_missing_files_are_skipped_gracefully(self, tmp_path, monkeypatch):
        """bump() should not crash when target files don't exist."""
        import bump_version as bv
        monkeypatch.setattr(bv, "__file__", str(tmp_path / "bump_version.py"))
        # No files created — should run without exception
        bump(dry_run=False)

    def test_rename_list_contains_ardware_intel_typo(self):
        """The RENAME list must include the original typo 'ardware_intel.py' so bump() can rename it."""
        old_names = [pair[0] for pair in RENAME]
        assert "ardware_intel.py" in old_names
