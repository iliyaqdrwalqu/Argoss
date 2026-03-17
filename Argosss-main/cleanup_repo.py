import os
import shutil
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class CleanupResult:
    removed_files: list[str] = field(default_factory=list)
    removed_dirs: list[str] = field(default_factory=list)
    freed_bytes: int = 0


def cleanup_repository(project: str | Path, input_func: Callable[[str], str] = input) -> CleanupResult:
    project_path = Path(project).resolve()
    result = CleanupResult()

    def has_path_part(path: str, name: str) -> bool:
        return name in Path(path).parts

    def rel(path: Path) -> str:
        return str(path).replace(str(project_path), "")

    def rm_file(path: Path) -> None:
        try:
            size = path.stat().st_size
            path.unlink()
            result.freed_bytes += size
            result.removed_files.append(rel(path))
        except Exception:
            pass

    def rm_dir(path: Path) -> None:
        try:
            size = sum((Path(root) / file).stat().st_size for root, _, files in os.walk(path) for file in files)
            shutil.rmtree(path)
            result.freed_bytes += size
            result.removed_dirs.append(rel(path))
        except Exception:
            pass

    print("🧹 Начинаю уборку...\n")

    for root, dirs, files in os.walk(project_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in [".git"]]

        for d in list(dirs):
            full = Path(root) / d

            if d == "__pycache__":
                rm_dir(full)
                dirs.remove(d)
            elif d == ".buildozer":
                print("  ⚠️  .buildozer найден — это может быть несколько ГБ!")
                answer = input_func("     Удалить .buildozer? (y/n): ").strip().lower()
                if answer == "y":
                    rm_dir(full)
                dirs.remove(d)
            elif d == "999" and "v1-3" in root:
                print(f"  🗑️  Дубликат: {rel(full)}")
                rm_dir(full)
                dirs.remove(d)

        for file_name in files:
            full = Path(root) / file_name

            if file_name.endswith(".pyc"):
                rm_file(full)
            elif ".ipynb_checkpoints" in root:
                rm_file(full)
            elif file_name.endswith((".log", ".tmp", ".bak")):
                rm_file(full)
            elif file_name in (".coverage", "coverage.xml"):
                rm_file(full)
            elif file_name == "__init__.py" and has_path_part(root, "999"):
                rm_file(full)

    for root, dirs, _ in os.walk(project_path):
        for d in dirs:
            if d == ".ipynb_checkpoints":
                rm_dir(Path(root) / d)

    freed_mb = result.freed_bytes / (1024 * 1024)

    print(f"\n{'═' * 50}")
    print("  🧹 УБОРКА ЗАВЕРШЕНА")
    print(f"{'═' * 50}")
    print(f"  Удалено файлов:  {len(result.removed_files)}")
    print(f"  Удалено папок:   {len(result.removed_dirs)}")
    print(f"  Освобождено:     {freed_mb:.1f} МБ")
    print(f"{'─' * 50}")
    if result.removed_dirs:
        print("  Папки:")
        for directory in result.removed_dirs[:10]:
            print(f"    🗂️  {directory}")
    if result.removed_files:
        print("  Файлы (первые 10):")
        for file_name in result.removed_files[:10]:
            print(f"    📄 {file_name}")
        if len(result.removed_files) > 10:
            print(f"    ... и ещё {len(result.removed_files) - 10}")
    print(f"{'═' * 50}")
    print("  ✅ Репозиторий убран!")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="ARGOS repository cleanup")
    parser.add_argument(
        "--project",
        default="/content/v1-3",
        help="Path to repository root (default: /content/v1-3)",
    )
    args = parser.parse_args()

    project = Path(args.project)
    os.chdir(project)
    cleanup_repository(project)


if __name__ == "__main__":
    main()
