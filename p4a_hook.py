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
                    f'''# {mod} disabled on Android\nraise ImportError("{mod} not available on Android")\n'''
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

    provider_xml = '''
    <provider
        android:name="androidx.core.content.FileProvider"
        android:authorities="${applicationId}.provider"
        android:exported="false"
        android:grantUriPermissions="true">
        <meta-data
            android:name="android.support.FILE_PROVIDER_PATHS"
            android:resource="@xml/file_paths" />
    </provider>
'''

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
        file_paths.write_text('''<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <external-path name="external_files" path="." />
    <files-path name="internal_files" path="." />
    <cache-path name="cache_files" path="." />
    <external-cache-path name="external_cache" path="." />
    <external-files-path name="external_app_files" path="." />
</paths>
''', encoding="utf-8")
        print("[p4a_hook] file_paths.xml создан")


def source_dirs(arch):
    fix_pyjnius(arch)
    disable_broken_modules(arch)


def postbuild_arch(arch, api, **kwargs):
    build_dir = getattr(arch, "build_dir", "")
    dist_dir  = getattr(arch, "dist_dir",  ".buildozer/android/platform/build")
    add_file_provider(build_dir or dist_dir)
    add_file_paths_xml(dist_dir)
