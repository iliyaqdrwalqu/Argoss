#!/usr/bin/env python3
"""
git_push.py — Автоматический коммит и пуш изменений в репозиторий ARGOS.

Использование:
  python git_push.py                        # коммит всех изменённых файлов
  python git_push.py -m "my message"        # с указанием сообщения коммита
  python git_push.py file1.py file2.py      # только конкретные файлы

Переменные окружения:
  GIT_TOKEN   — Personal Access Token для пуша (опционально; нужен для HTTPS-пуша без кэшированных credentials)
  GIT_USER    — git user.name (по умолчанию: ARGOS AutoPush)
  GIT_EMAIL   — git user.email (по умолчанию: argos@sigtrip.dev)
  GIT_BRANCH  — ветка для пуша (по умолчанию: текущая ветка)
"""
import os
import subprocess
import sys
import argparse

# ─── Настройки по умолчанию ──────────────────────────────────────────────────
DEFAULT_USER   = "ARGOS AutoPush"
DEFAULT_EMAIL  = "argos@sigtrip.dev"
DEFAULT_MSG    = "chore: автоматический коммит изменений [skip ci]"

def run(cmd, cwd=None, check=True, capture=True):
    """Выполняет команду и выводит результат."""
    print(f"$ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=cwd,
        capture_output=capture, text=True,
    )
    if capture:
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"❌ Ошибка (код {result.returncode})")
        sys.exit(1)
    return result

def get_repo_root() -> str:
    """Возвращает корневой каталог git-репозитория."""
    result = subprocess.run(
        "git rev-parse --show-toplevel",
        shell=True, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("❌ Текущий каталог не является git-репозиторием.")
        sys.exit(1)
    return result.stdout.strip()

def current_branch() -> str:
    result = subprocess.run(
        "git rev-parse --abbrev-ref HEAD",
        shell=True, capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "main"

def inject_token_into_remote(token: str) -> str | None:
    """Встраивает токен в URL remote origin для HTTPS-пуша.

    Возвращает оригинальный URL (если он был изменён), чтобы вызывающий код
    мог восстановить его после пуша вызовом:
        git remote set-url origin <original_url>
    Если URL уже содержит credentials или не является HTTPS — возвращает None
    и ничего не меняет."""
    result = subprocess.run(
        "git remote get-url origin",
        shell=True, capture_output=True, text=True,
    )
    original_url = result.stdout.strip()
    if original_url.startswith("https://") and "@" not in original_url:
        # https://github.com/... → https://<token>@github.com/...
        new_url = original_url.replace("https://", f"https://{token}@")
        subprocess.run(f"git remote set-url origin {new_url}", shell=True)
        return original_url  # caller must restore this after push
    return None

def main():
    parser = argparse.ArgumentParser(description="Auto-commit and push to ARGOS repo")
    parser.add_argument("files", nargs="*", help="Файлы для добавления (по умолчанию: все изменения)")
    parser.add_argument("-m", "--message", default=None, help="Сообщение коммита")
    parser.add_argument("-b", "--branch", default=None, help="Ветка для пуша")
    args = parser.parse_args()

    # Определяем каталог репозитория
    repo_dir = get_repo_root()
    os.chdir(repo_dir)
    print(f"📁 Репозиторий: {repo_dir}\n")

    # Настройка git identity
    git_user  = os.environ.get("GIT_USER",  DEFAULT_USER)
    git_email = os.environ.get("GIT_EMAIL", DEFAULT_EMAIL)
    run(f'git config user.name  "{git_user}"')
    run(f'git config user.email "{git_email}"')

    # Если задан токен — встраиваем в remote URL временно
    token = os.environ.get("GIT_TOKEN", "")
    original_remote_url = None
    if token:
        original_remote_url = inject_token_into_remote(token)

    # Добавляем файлы
    if args.files:
        for f in args.files:
            if os.path.exists(f):
                run(f"git add -- {f}")
                print(f"✅ Добавлен: {f}")
            else:
                print(f"⚠️  Файл не найден, пропускаю: {f}")
    else:
        run("git add -A")
        print("✅ Добавлены все изменения (git add -A)")

    # Проверяем есть ли что коммитить
    diff = run("git diff --cached --name-only", check=False)
    if not diff.stdout.strip():
        print("\n⚠️  Нечего коммитить — нет изменений в индексе.")
        sys.exit(0)

    # Коммит
    commit_msg = args.message or os.environ.get("GIT_COMMIT_MSG", DEFAULT_MSG)
    run(f'git commit -m "{commit_msg}"')
    print("\n✅ Коммит создан!\n")

    # Пуш
    branch = args.branch or os.environ.get("GIT_BRANCH", current_branch())
    try:
        push = run(f"git push origin {branch}", check=False)
    finally:
        # Восстанавливаем оригинальный URL, чтобы токен не остался в git-конфиге
        if original_remote_url:
            subprocess.run(
                f"git remote set-url origin {original_remote_url}", shell=True
            )
    if push.returncode != 0:
        print(f"\n❌ Пуш в ветку '{branch}' не удался.")
        print("   Проверьте права доступа или укажите GIT_TOKEN.")
        sys.exit(1)

    print(f"\n🚀 Изменения успешно запушены в {branch}!")

if __name__ == "__main__":
    main()

