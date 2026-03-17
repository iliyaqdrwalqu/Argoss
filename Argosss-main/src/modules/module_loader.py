from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Iterable

from src.argos_logger import get_logger
from src.modules.base import BaseModule

log = get_logger("argos.modules")


class ModuleLoader:
    def __init__(self, package: str = "src.modules"):
        self.package = package
        self.modules: dict[str, BaseModule] = {}

    def _iter_candidates(self) -> Iterable[str]:
        pkg = importlib.import_module(self.package)
        for info in pkgutil.iter_modules(pkg.__path__):
            if info.name in {"base", "module_loader", "__init__"}:
                continue
            if not info.name.endswith("_module"):
                continue
            yield f"{self.package}.{info.name}"

    def load_all(self, core=None) -> str:
        loaded = []
        errors = []
        for mod_path in self._iter_candidates():
            try:
                py_mod = importlib.import_module(mod_path)
                for _, obj in inspect.getmembers(py_mod, inspect.isclass):
                    if not issubclass(obj, BaseModule) or obj is BaseModule:
                        continue
                    instance: BaseModule = obj()
                    if core:
                        instance.setup(core)
                    self.modules[instance.module_id] = instance
                    loaded.append(instance.module_id)
                    log.info("Модуль загружен: %s (%s)", instance.module_id, mod_path)
            except Exception as e:
                errors.append(f"{mod_path}: {e}")
                log.warning("Module load failed %s: %s", mod_path, e)

        lines = [f"🧩 Modules: {len(loaded)} загружено"]
        if loaded:
            lines.append("  " + ", ".join(sorted(loaded)))
        if errors:
            lines.append("⚠ Ошибки:")
            lines.extend(f"  - {x}" for x in errors[:10])
        return "\n".join(lines)

    def dispatch(self, text: str, admin=None, flasher=None) -> str | None:
        lowered = text.lower()
        for mod in self.modules.values():
            try:
                if mod.can_handle(text, lowered):
                    result = mod.handle(text, lowered, admin=admin, flasher=flasher)
                    if result:
                        return result
            except Exception as e:
                log.error("Module '%s' error: %s", mod.module_id, e)
        return None

    def list_modules(self) -> str:
        if not self.modules:
            return "🧩 Модули не загружены."
        lines = ["🧩 ЗАГРУЖЕННЫЕ МОДУЛИ:"]
        for mod in sorted(self.modules.values(), key=lambda m: m.module_id):
            lines.append(f"  • {mod.module_id:16s} — {mod.title}")
        return "\n".join(lines)
