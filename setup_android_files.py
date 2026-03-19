#!/usr/bin/env python3
"""
setup_android_files.py — Создаёт файлы FileProvider для исправления SAI ошибки.

ПРОБЛЕМА:
  SAI (Split APKs Installer) падает с BadContentProviderException: DISPLAY_NAME is null
  потому что Android ContentProvider не возвращает метаданные файла.

РЕШЕНИЕ:
  Добавить androidx.core.content.FileProvider в AndroidManifest.xml
  с правильными путями — тогда DISPLAY_NAME будет заполнен автоматически.

Запуск: python setup_android_files.py
"""
from pathlib import Path
import subprocess
import sys


# ─────────────────────────────────────────────────────────────────────────────
# 1. res/xml/file_paths.xml — описывает какие пути доступны через FileProvider
# ─────────────────────────────────────────────────────────────────────────────
FILE_PATHS_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <!-- Внешнее хранилище (Downloads, Documents) -->
    <external-path
        name="external_files"
        path="." />
    <!-- Внутреннее хранилище приложения -->
    <files-path
        name="internal_files"
        path="." />
    <!-- Кэш приложения -->
    <cache-path
        name="cache_files"
        path="." />
    <!-- Внешний кэш -->
    <external-cache-path
        name="external_cache"
        path="." />
    <!-- Для Android 10+ (scoped storage) -->
    <external-files-path
        name="external_app_files"
        path="." />
</paths>
"""

# ─────────────────────────────────────────────────────────────────────────────
# 2. Фрагмент AndroidManifest.xml для FileProvider
#    Вставляется внутрь <application> тега
# ─────────────────────────────────────────────────────────────────────────────
PROVIDER_MANIFEST_XML = """\
<!-- [FIX-SAI-FILEPROVIDER] FileProvider для корректной передачи имён файлов -->
<provider
    android:name="androidx.core.content.FileProvider"
    android:authorities="${applicationId}.provider"
    android:exported="false"
    android:grantUriPermissions="true">
    <meta-data
        android:name="android.support.FILE_PROVIDER_PATHS"
        android:resource="@xml/file_paths" />
</provider>
"""

# ─────────────────────────────────────────────────────────────────────────────
# 3. p4a_hook.py — хук Python-for-Android для патча AndroidManifest после сборки
# ─────────────────────────────────────────────────────────────────────────────
P4A_HOOK = '''\
"""
p4a_hook.py — Хук Python-for-Android.
Патчит pyjnius для Python 3, отключает несовместимые C-модули,
и добавляет FileProvider в AndroidManifest.xml.
"""
import os
import re
from pathlib import Path


def fix_pyjnius(arch):
    """Фикс pyjnius для Python 3 (убирает использование 'long')."""
    site_packages = arch.get_env_vars().get("PYTHONPATH", "")
    for sp in site_packages.split(":"):
        jnius_src = Path(sp) / "jnius" / "jnius_utils.pxi"
        if jnius_src.exists():
            content = jnius_src.read_text(errors="replace")
            if "long(" in content:
                content = content.replace("long(", "int(")
                jnius_src.write_text(content)
                print("[p4a_hook] pyjnius: убрал long() → int()")


def disable_broken_modules(arch):
    """Отключает C-модули несовместимые с Android."""
    broken = ["grp", "_uuid", "_lzma"]
    site_packages = arch.get_env_vars().get("PYTHONPATH", "")
    for sp in site_packages.split(":"):
        for mod in broken:
            path = Path(sp) / f"{mod}.py"
            if not path.exists():
                path.write_text(
                    f\'\'\'# {mod} disabled on Android\\nraise ImportError("{mod} not available on Android")\\n\'\'\'
                )


def add_file_provider(build_dir):
    """Добавляет FileProvider в AndroidManifest.xml."""
    manifest_path = Path(build_dir) / "AndroidManifest.xml"
    if not manifest_path.exists():
        # Ищем в .buildozer
        for p in Path(".buildozer").rglob("AndroidManifest.xml"):
            manifest_path = p
            break

    if not manifest_path.exists():
        print("[p4a_hook] AndroidManifest.xml не найден — пропускаю FileProvider")
        return

    content = manifest_path.read_text(encoding="utf-8", errors="replace")

    if "FileProvider" in content:
        print("[p4a_hook] FileProvider уже в манифесте")
        return

    provider_xml = \'\'\'
    <provider
        android:name="androidx.core.content.FileProvider"
        android:authorities="${applicationId}.provider"
        android:exported="false"
        android:grantUriPermissions="true">
        <meta-data
            android:name="android.support.FILE_PROVIDER_PATHS"
            android:resource="@xml/file_paths" />
    </provider>
\'\'\'

    # Вставляем перед </application>
    if "</application>" in content:
        content = content.replace("</application>", provider_xml + "</application>", 1)
        manifest_path.write_text(content, encoding="utf-8")
        print("[p4a_hook] FileProvider добавлен в AndroidManifest.xml")
    else:
        print("[p4a_hook] </application> не найден — FileProvider не добавлен")


def add_file_paths_xml(dist_dir):
    """Создаёт res/xml/file_paths.xml в дистрибутиве."""
    xml_dir = Path(dist_dir) / "res" / "xml"
    xml_dir.mkdir(parents=True, exist_ok=True)
    file_paths = xml_dir / "file_paths.xml"
    if not file_paths.exists():
        file_paths.write_text(\'\'\'<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <external-path name="external_files" path="." />
    <files-path name="internal_files" path="." />
    <cache-path name="cache_files" path="." />
    <external-cache-path name="external_cache" path="." />
    <external-files-path name="external_app_files" path="." />
</paths>
\'\'\', encoding="utf-8")
        print("[p4a_hook] file_paths.xml создан")


def source_dirs(arch):
    fix_pyjnius(arch)
    disable_broken_modules(arch)


def postbuild_arch(arch, api, **kwargs):
    build_dir = getattr(arch, "build_dir", "")
    dist_dir  = getattr(arch, "dist_dir",  ".buildozer/android/platform/build")
    add_file_provider(build_dir or dist_dir)
    add_file_paths_xml(dist_dir)
'''


def main():
    print("🔧 Настройка Android FileProvider для ARGOS...\n")

    # 1. res/xml/file_paths.xml
    xml_dir = Path("res/xml")
    xml_dir.mkdir(parents=True, exist_ok=True)
    file_paths_xml = xml_dir / "file_paths.xml"
    file_paths_xml.write_text(FILE_PATHS_XML, encoding="utf-8")
    print(f"✅ Создан: {file_paths_xml}")

    # 2. Обновляем p4a_hook.py
    hook_path = Path("p4a_hook.py")
    hook_path.write_text(P4A_HOOK, encoding="utf-8")
    print(f"✅ Обновлён: {hook_path}")

    # 3. Создаём директорию .buildozer/android/platform/ если нужно
    provider_dir = Path(".buildozer/android/platform")
    provider_dir.mkdir(parents=True, exist_ok=True)
    provider_meta = provider_dir / "provider_meta.xml"
    provider_meta.write_text(PROVIDER_MANIFEST_XML, encoding="utf-8")
    print(f"✅ Создан: {provider_meta}")

    # 4. Проверяем main_kivy.py на наличие KIVY_NO_ARGS
    main_kivy = Path("main_kivy.py")
    if main_kivy.exists():
        content = main_kivy.read_text(encoding="utf-8", errors="replace")
        if "KIVY_NO_ARGS" not in content:
            # Добавляем в начало
            new_content = 'import os\nos.environ.setdefault("KIVY_NO_ARGS", "1")\n\n' + content
            main_kivy.write_text(new_content, encoding="utf-8")
            print("✅ KIVY_NO_ARGS добавлен в main_kivy.py")
    else:
        print("⚠️  main_kivy.py не найден — создай его для Android сборки")

    print("\n" + "─" * 50)
    print("✅ Готово! Теперь:")
    print("  1. Убедись что buildozer.spec обновлён (скачан выше)")
    print("  2. Для локальной сборки: buildozer android debug")
    print("  3. Для GitHub Actions: git push — APK соберётся автоматически")
    print("\nAPK будет в папке bin/")
    print("При установке через SAI ошибка DISPLAY_NAME исчезнет.")


if __name__ == "__main__":
    main()
