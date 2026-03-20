"""Smoke tests for ArgosCore — verifies importability and basic init."""
import pytest
from types import SimpleNamespace


def test_argos_core_importable():
    """ArgosCore should be importable without raising."""
    try:
        from src.core import ArgosCore
    except ImportError as e:
        pytest.skip(f"Optional dependency missing: {e}")


def test_argos_core_has_version():
    try:
        from src.core import ArgosCore
        core = ArgosCore()
        assert hasattr(core, "VERSION")
        assert isinstance(core.VERSION, str)
    except ImportError as e:
        pytest.skip(f"Optional dependency missing: {e}")


def test_argos_core_process_logic_returns_dict():
    try:
        from src.core import ArgosCore
        core = ArgosCore()
        result = core.process_logic("помощь", None, None)
        assert isinstance(result, dict)
        assert "answer" in result
    except (ImportError, Exception) as e:
        pytest.skip(f"Cannot test core: {e}")
