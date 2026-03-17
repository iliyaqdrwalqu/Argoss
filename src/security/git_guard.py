"""
git_guard.py — Защита .env и секретных файлов от попадания в Git.
Проверяет .gitignore, pre-commit hook, наличие ключей в коде.
"""
import os
import re
import subprocess
from pathlib import Path
from src.argos_logger import get_logger

log = get_logger("argos.git_guard")

SENSITIVE_PATTERNS = [
    r"GEMINI_API_KEY\s*=\s*['\"][A-Za-z0-9_-]{10,}",
    r"TELEGRAM_BOT_TOKEN\s*=\s*['\"][0-9]+:[A-Za-z0-9_-]{30,}",
    r"ARGOS_MASTER_KEY\s*=\s*['\"][0-9a-f]{32,}",
    r"ARGOS_NETWORK_SECRET\s*=\s*['\"][0-9a-f]{32,}",
    r"password\s*=\s*['\"][\w@#$%^&*]{8,}",
    r"secret\s*=\s*['\"][\w@#$%^&*]{8,}",
]

REQUIRED_GITIGNORE = [
    ".env",
    "config/master.key",
    "config/node_id",
    "config/node_birth",
    "*.key",
    "*.pem",
    "*.p12",
    "logs/",
    "__pycache__/",
    "*.pyc",
    ".DS_Store",
    "venv/",
    ".venv/",
    "dist/",
    "builds/",
]


class GitGuard:
    def __init__(self, repo_root: str = "."):
        self.root = Path(repo_root).resolve()
        self.gitignore = self.root / ".gitignore"

    def check_gitignore(self) -> str:
        """Проверяет .gitignore на наличие всех обязательных строк."""
        if not self.gitignore.exists():
            return "⚠️ GitGuard: .gitignore не найден! Создаю..."

        content = self.gitignore.read_text(encoding="utf-8")
        missing = [p for p in REQUIRED_GITIGNORE if p not in content]

        if missing:
            with open(self.gitignore, "a", encoding="utf-8") as f:
                f.write("\n# === Argos GitGuard ===\n")
                for m in missing:
                    f.write(m + "\n")
            return f"✅ GitGuard: добавлено {len(missing)} записей в .gitignore"
        return "✅ GitGuard: .gitignore в порядке"

    def scan_secrets(self, path: str = "src") -> str:
        """Сканирует исходники на наличие хардкоженных секретов."""
        found = []
        scan_path = self.root / path
        if not scan_path.exists():
            return f"⚠️ Путь {path} не найден"

        for py_file in scan_path.rglob("*.py"):
            try:
                text = py_file.read_text(encoding="utf-8", errors="ignore")
                for pattern in SENSITIVE_PATTERNS:
                    if re.search(pattern, text, re.IGNORECASE):
                        found.append(str(py_file.relative_to(self.root)))
                        break
            except Exception:
                pass

        if found:
            return ("🚨 GitGuard: найдены возможные секреты в коде:\n" +
                    "\n".join(f"  ⚠️ {f}" for f in found[:20]))
        return "✅ GitGuard: секреты в исходниках не обнаружены"

    def install_pre_commit_hook(self) -> str:
        """Устанавливает pre-commit hook для блокировки коммитов с секретами."""
        hooks_dir = self.root / ".git" / "hooks"
        if not hooks_dir.exists():
            return "⚠️ GitGuard: .git/hooks не найден (не git-репозиторий?)"

        hook_path = hooks_dir / "pre-commit"
        hook_content = """#!/bin/sh
# Argos GitGuard pre-commit hook
python -c "
import sys, re, subprocess
patterns = [
    r\"GEMINI_API_KEY\\s*=\\s*[A-Za-z0-9_-]{10,}\",
    r\"TELEGRAM_BOT_TOKEN\\s*=\\s*[0-9]+:[A-Za-z0-9_-]{30,}\",
]
result = subprocess.run(['git', 'diff', '--cached', '--', '*.py', '*.env'],
                        capture_output=True, text=True)
for p in patterns:
    if re.search(p, result.stdout):
        print('🚨 Найден секрет в коммите! Коммит отменён.')
        sys.exit(1)
"
"""
        try:
            hook_path.write_text(hook_content)
            hook_path.chmod(0o755)
            return f"✅ GitGuard: pre-commit hook установлен → {hook_path}"
        except Exception as e:
            return f"❌ GitGuard hook: {e}"

    def status(self) -> str:
        gi = "✅" if self.gitignore.exists() else "❌"
        hook = "✅" if (self.root / ".git" / "hooks" / "pre-commit").exists() else "⚠️"
        return (
            f"🛡️ GIT GUARD:\n"
            f"  .gitignore:    {gi}\n"
            f"  pre-commit:    {hook}\n"
            f"  Корень:        {self.root}"
        )

    def full_check(self) -> str:
        lines = [
            "🛡️ GIT GUARD — полная проверка:",
            self.check_gitignore(),
            self.scan_secrets(),
        ]
        return "\n".join(lines)

    def check_security(self) -> str:
        return self.full_check()
