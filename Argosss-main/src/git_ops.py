"""
git_ops.py — Управление Git-операциями из Аргоса
  Безопасные операции status/add/commit/push через subprocess без shell=True.
"""
import os
import subprocess

from src.argos_logger import get_logger

log = get_logger("argos.gitops")


class ArgosGitOps:
    def __init__(self, repo_path: str = "."):
        self.repo_path = os.path.abspath(repo_path)

    def _run(self, *args: str, timeout: int = 40) -> tuple[int, str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out.strip()

    def _is_repo(self) -> bool:
        code, _ = self._run("rev-parse", "--is-inside-work-tree")
        return code == 0

    def _current_branch(self) -> str:
        code, out = self._run("rev-parse", "--abbrev-ref", "HEAD")
        if code == 0 and out:
            return out.strip()
        return "main"

    def _remote_name(self) -> str:
        code, out = self._run("remote")
        if code != 0:
            return "origin"
        remotes = [x.strip() for x in out.splitlines() if x.strip()]
        if "origin" in remotes:
            return "origin"
        return remotes[0] if remotes else "origin"

    def status(self) -> str:
        if not self._is_repo():
            return "❌ Текущая директория не является Git-репозиторием."

        code_branch, branch = self._run("rev-parse", "--abbrev-ref", "HEAD")
        code_status, short = self._run("status", "--short")
        if code_status != 0:
            return f"❌ Git status error:\n{short[:500]}"

        if not short.strip():
            return f"🌿 Git: рабочее дерево чистое (branch={branch.strip() if code_branch == 0 else 'unknown'})."

        lines = short.splitlines()[:20]
        suffix = "\n..." if len(short.splitlines()) > 20 else ""
        return (
            f"🌿 Git status ({branch.strip() if code_branch == 0 else 'unknown'}):\n"
            + "\n".join(lines)
            + suffix
        )

    def commit(self, message: str) -> str:
        if not self._is_repo():
            return "❌ Текущая директория не является Git-репозиторием."

        msg = (message or "").strip()
        if not msg:
            return "❌ Пустое сообщение коммита. Формат: git коммит <сообщение>."

        code, short = self._run("status", "--short")
        if code != 0:
            return f"❌ Не удалось получить status:\n{short[:400]}"
        if not short.strip():
            return "ℹ️ Нет изменений для коммита."

        add_code, add_out = self._run("add", "-A")
        if add_code != 0:
            return f"❌ git add error:\n{add_out[:500]}"

        commit_code, commit_out = self._run("commit", "-m", msg, timeout=60)
        if commit_code != 0:
            return f"❌ git commit error:\n{commit_out[:700]}"
        return f"✅ Коммит создан:\n{commit_out[:700]}"

    def push(self) -> str:
        if not self._is_repo():
            return "❌ Текущая директория не является Git-репозиторием."

        remote = self._remote_name()
        branch = self._current_branch()
        code, out = self._run("push", remote, branch, timeout=90)
        if code != 0:
            return f"❌ git push error:\n{out[:800]}"
        return f"🚀 Push выполнен: {remote}/{branch}\n{out[:700]}"

    def commit_and_push(self, message: str) -> str:
        commit_res = self.commit(message)
        if commit_res.startswith("❌"):
            return commit_res
        if commit_res.startswith("ℹ️"):
            return commit_res
        push_res = self.push()
        return f"{commit_res}\n\n{push_res}"
