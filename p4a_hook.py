"""
python-for-android build hook.

Applies patches required to build pyjnius with modern Cython + Python 3:
  - Replaces the Python-2-only ``long`` built-in with ``int`` in
    ``jnius_utils.pxi`` so Cython 3.x / Python 3 can compile it.

Also disables Python stdlib C extensions that cannot be built against the
Android NDK (no grp/group, no libuuid, no liblzma in the NDK sysroot):
  - grp
  - _uuid
  - _lzma
"""

from __future__ import annotations

import glob
import os
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_long_to_int(path: str) -> None:
    """Replace ``isinstance(x, long)`` with ``isinstance(x, int)`` in *path*."""
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    patched = re.sub(
        r"\bisinstance\(([^,]+),\s*long\)",
        r"isinstance(\1, int)",
        src,
    )
    if patched == src:
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patched)
    print(f"[p4a_hook] Patched 'long' -> 'int' in: {path}")


# ---------------------------------------------------------------------------
# p4a hook entry-points
# ---------------------------------------------------------------------------

def before_build(toolchain) -> None:
    """Called by p4a before any recipe is built."""
    _fix_pyjnius(toolchain)
    _disable_android_incompatible_modules(toolchain)


# ---------------------------------------------------------------------------
# Patch implementations
# ---------------------------------------------------------------------------

def _fix_pyjnius(toolchain) -> None:
    """
    Patch jnius_utils.pxi to remove the Python-2-only ``long`` built-in.

    Cython 3 raises ``undeclared name not builtin: long`` because ``long``
    no longer exists in Python 3.  Replace every occurrence of
    ``isinstance(x, long)`` with ``isinstance(x, int)``.
    """
    storage = getattr(toolchain, "storage_dir", None) or ""
    search_roots = [
        storage,
        os.path.expanduser("~/.buildozer"),
        os.getcwd(),
    ]
    for root in search_roots:
        if not root:
            continue
        for match in glob.glob(
            os.path.join(root, "**", "jnius_utils.pxi"), recursive=True
        ):
            _patch_long_to_int(match)


def _disable_android_incompatible_modules(toolchain) -> None:
    """
    Prevent Python-for-Android from trying to build stdlib C extensions
    that depend on headers / libraries absent from the Android NDK sysroot:

      * grp   – POSIX group-database functions (setgrent / getgrent …)
      * _uuid – requires libuuid (not bundled with Android NDK)
      * _lzma – requires liblzma / lzma.h (not bundled with Android NDK)
    """
    incompatible = {"grp", "_uuid", "_lzma"}
    try:
        from pythonforandroid.recipes.python3 import Python3Recipe  # type: ignore[import]

        existing = set(getattr(Python3Recipe, "disabled_modules", []))
        new_disabled = sorted(existing | incompatible)
        Python3Recipe.disabled_modules = new_disabled
        added = incompatible - existing
        if added:
            print(
                f"[p4a_hook] Added to Python3Recipe.disabled_modules: "
                f"{', '.join(sorted(added))}"
            )
    except Exception as exc:  # noqa: BLE001
        print(
                f"[p4a_hook] WARNING: Could not patch Python3Recipe.disabled_modules "
                f"({exc}). The build may still succeed if p4a already excludes "
                f"grp/_uuid/_lzma for Android, but watch for NDK linker errors."
            )
