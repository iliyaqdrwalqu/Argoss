import argparse
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


KEEP_ROOT = {
    "main.py",
    "genesis.py",
    "README.md",
    "requirements.txt",
    ".env",
    ".env.example",
    ".gitignore",
    "docker-compose.yml",
    "Dockerfile",
}


@dataclass
class OrganizationResult:
    moved: list[str] = field(default_factory=list)
    root_files: list[str] = field(default_factory=list)
    root_dirs: list[str] = field(default_factory=list)


def _move_from_root(project_path: Path, src: str, dst_dir: str, moved: list[str]) -> None:
    src_path = project_path / src
    if not src_path.exists() or not src_path.is_file():
        return

    dst_folder = project_path / dst_dir
    dst_folder.mkdir(parents=True, exist_ok=True)
    dst_path = dst_folder / src_path.name
    if dst_path.exists():
        return

    shutil.move(str(src_path), str(dst_path))
    moved.append(f"  📄 {src}  →  {dst_dir}/")


def organize_files(project: str | Path = ".") -> OrganizationResult:
    project_path = Path(project).resolve()
    result = OrganizationResult()

    print("📁 Организация файлов...\n")

    for file_name in [
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "QUICK_START.md",
        "QUICKSTART.md",
        "SECURITY.md",
        "METRICS.md",
        "RELEASE_NOTES_v1.3.md",
        "FINAL_REPORT.md",
        "APK_BUILD_REPORT.md",
        "AUDIT_FIXES_SUMMARY.md",
        "mkdocs.yml",
    ]:
        _move_from_root(project_path, file_name, "docs", result.moved)

    for file_name in [
        "build_apk.py",
        "build_exe.py",
        "setup_builder.py",
        "setup_secrets.py",
        "health_check.py",
        "trainer.py",
        "db_init.py",
        "check_readiness.py",
        "deploy.sh",
        "create_release.sh",
        "install_windows.bat",
        "run_windows.bat",
        "setup_argos.nsi",
        "setup_argos.exe",
        "Makefile",
        "pyproject.toml",
        "mypy.ini",
        ".flake8",
        ".pre-commit-config.yaml",
    ]:
        _move_from_root(project_path, file_name, "scripts", result.moved)

    for file_name in ["Dockerfile.windows", "argos.service"]:
        _move_from_root(project_path, file_name, "docker", result.moved)

    for file_name in [
        "Untitled6.ipynb",
        "Argos_Master_Core_Part_1.ipynb",
        'Копия_блокнота_"Untitled7_ipynb".ipynb',
    ]:
        _move_from_root(project_path, file_name, "notebooks", result.moved)

    for file_name in ["argos_startup_log.txt", ".coverage"]:
        _move_from_root(project_path, file_name, "reports", result.moved)

    for path in list(project_path.iterdir()):
        if path.is_file() and path.suffix == ".ipynb" and path.name not in KEEP_ROOT:
            _move_from_root(project_path, path.name, "notebooks", result.moved)

    for path in list(project_path.iterdir()):
        if path.is_file() and path.suffix == ".md" and path.name not in KEEP_ROOT:
            _move_from_root(project_path, path.name, "docs", result.moved)

    for path in list(project_path.iterdir()):
        if path.is_file() and path.suffix == ".txt" and path.name not in KEEP_ROOT:
            _move_from_root(project_path, path.name, "reports", result.moved)

    print("Перемещено:")
    for item in result.moved:
        print(item)

    print(f"\n{'═' * 50}")
    print("  📁 СТРУКТУРА ГЛАВНОЙ СТРАНИЦЫ")
    print(f"{'═' * 50}")

    result.root_files = sorted(
        [
            f.name
            for f in project_path.iterdir()
            if f.is_file() and not f.name.startswith(".")
        ]
    )
    result.root_dirs = sorted(
        [
            d.name
            for d in project_path.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"
        ]
    )

    print("\n  📄 Файлы:")
    for file_name in result.root_files:
        tag = "⭐" if file_name in KEEP_ROOT else "📄"
        print(f"    {tag} {file_name}")

    print("\n  📁 Папки:")
    for directory in result.root_dirs:
        file_count = sum(len(files) for _, _, files in os.walk(project_path / directory))
        print(f"    📂 {directory}/  ({file_count} файлов)")

    print(f"\n{'═' * 50}")
    print(f"  Перемещено: {len(result.moved)} файлов")
    print("  ✅ Готово!")
    print(f"{'═' * 50}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="ARGOS file organizer")
    parser.add_argument(
        "--project",
        default=".",
        help="Path to repository root (default: current directory)",
    )
    args = parser.parse_args()
    organize_files(args.project)


if __name__ == "__main__":
    main()
