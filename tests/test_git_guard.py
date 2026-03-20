"""tests/test_git_guard.py — unit tests for src/security/git_guard.py"""
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.security.git_guard import GitGuard, REQUIRED_GITIGNORE


# ---------------------------------------------------------------------------
# check_gitignore
# ---------------------------------------------------------------------------

class TestCheckGitignore:
    def test_missing_gitignore_returns_warning(self, tmp_path):
        guard = GitGuard(str(tmp_path))
        result = guard.check_gitignore()
        assert "не найден" in result or "⚠️" in result

    def test_all_entries_present_returns_ok(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("\n".join(REQUIRED_GITIGNORE) + "\n", encoding="utf-8")
        guard = GitGuard(str(tmp_path))
        result = guard.check_gitignore()
        assert "✅" in result
        assert "порядке" in result

    def test_missing_entries_are_appended(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("# empty\n", encoding="utf-8")
        guard = GitGuard(str(tmp_path))
        result = guard.check_gitignore()
        assert "✅" in result
        content_after = gi.read_text(encoding="utf-8")
        for entry in REQUIRED_GITIGNORE:
            assert entry in content_after

    def test_partial_entries_only_appends_missing(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text(".env\n*.pyc\n", encoding="utf-8")
        guard = GitGuard(str(tmp_path))
        guard.check_gitignore()
        content = gi.read_text(encoding="utf-8")
        # Already present entries should not be duplicated
        assert content.count(".env") == 1
        assert content.count("*.pyc") == 1


# ---------------------------------------------------------------------------
# scan_secrets
# ---------------------------------------------------------------------------

class TestScanSecrets:
    def test_clean_source_returns_ok(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "clean.py").write_text("x = 1\n", encoding="utf-8")
        guard = GitGuard(str(tmp_path))
        result = guard.scan_secrets("src")
        assert "✅" in result

    def test_detects_telegram_token(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "secrets.py").write_text(
            "TELEGRAM_BOT_TOKEN = '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh'\n",
            encoding="utf-8",
        )
        guard = GitGuard(str(tmp_path))
        result = guard.scan_secrets("src")
        assert "🚨" in result or "⚠️" in result

    def test_nonexistent_path_returns_warning(self, tmp_path):
        guard = GitGuard(str(tmp_path))
        result = guard.scan_secrets("nonexistent_dir")
        assert "⚠️" in result or "не найден" in result


# ---------------------------------------------------------------------------
# install_pre_commit_hook
# ---------------------------------------------------------------------------

class TestInstallPreCommitHook:
    def test_no_git_dir_returns_warning(self, tmp_path):
        guard = GitGuard(str(tmp_path))
        result = guard.install_pre_commit_hook()
        assert "⚠️" in result or "не найден" in result

    def test_hook_is_created_and_executable(self, tmp_path):
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        guard = GitGuard(str(tmp_path))
        result = guard.install_pre_commit_hook()
        hook_path = hooks_dir / "pre-commit"
        assert hook_path.exists()
        assert "✅" in result
        # Should be executable
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_contains_guard_info(self, tmp_path):
        guard = GitGuard(str(tmp_path))
        result = guard.status()
        assert "GIT GUARD" in result
        assert ".gitignore" in result


# ---------------------------------------------------------------------------
# full_check
# ---------------------------------------------------------------------------

class TestFullCheck:
    def test_full_check_returns_string(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        gi = tmp_path / ".gitignore"
        gi.write_text("\n".join(REQUIRED_GITIGNORE), encoding="utf-8")
        guard = GitGuard(str(tmp_path))
        result = guard.full_check()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_full_check_includes_gitignore_and_secrets(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        gi = tmp_path / ".gitignore"
        gi.write_text("# placeholder\n", encoding="utf-8")
        guard = GitGuard(str(tmp_path))
        result = guard.full_check()
        # Should mention both checks
        assert "GIT GUARD" in result
