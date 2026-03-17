import builtins
import importlib.util
from pathlib import Path


def test_root_package_init_does_not_eagerly_import_netghost(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "src.skills.net_scanner.skill":
            raise AssertionError("root package should not import NetGhost during module import")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module_path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("argos_root_init_test", module_path)
    module = importlib.util.module_from_spec(spec)

    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.__all__ == ["NetGhost"]
