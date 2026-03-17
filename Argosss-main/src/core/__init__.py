from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_LEGACY_CORE_MODULE = "src._argos_core_impl"
_LEGACY_CORE_PATH = Path(__file__).resolve().parents[1] / "core.py"

def _load_argos_core_class():
    if _LEGACY_CORE_MODULE in sys.modules:
        return sys.modules[_LEGACY_CORE_MODULE].ArgosCore

    _spec = spec_from_file_location(_LEGACY_CORE_MODULE, _LEGACY_CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Cannot load ArgosCore from {_LEGACY_CORE_PATH}")
    _core_impl = module_from_spec(_spec)
    sys.modules[_LEGACY_CORE_MODULE] = _core_impl
    _spec.loader.exec_module(_core_impl)
    return _core_impl.ArgosCore


class _LazyArgosCoreMeta(type):
    def __getattr__(cls, item):
        return getattr(_load_argos_core_class(), item)

    def __setattr__(cls, item, value):
        # During metaclass machinery (dunder attrs) keep on the class itself.
        if item.startswith("__") and item.endswith("__"):
            super().__setattr__(item, value)
            return
        # Forward all non-dunder writes to the real implementation class so
        # that class-level state (e.g. _ollama_proc) is shared between the
        # lazy proxy and the actual ArgosCore defined in src/core.py.
        # Note: if the impl is not yet loaded at write time, the attribute is
        # stored on the proxy stub (via super().__setattr__) and the impl's own
        # class-level defaults take precedence once it loads.  In practice the
        # impl is always already cached in sys.modules before tests set class
        # attributes, so this edge case is safe to ignore.
        if _LEGACY_CORE_MODULE in sys.modules:
            impl_mod = sys.modules[_LEGACY_CORE_MODULE]
            real_cls = getattr(impl_mod, "ArgosCore", None)
            if real_cls is not None:
                setattr(real_cls, item, value)
                return
        super().__setattr__(item, value)

    def __call__(cls, *args, **kwargs):
        return _load_argos_core_class()(*args, **kwargs)


class ArgosCore(metaclass=_LazyArgosCoreMeta):
    pass

__all__ = ["ArgosCore"]
