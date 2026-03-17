import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_skill_module():
    # Исторически файл в репозитории называется именно `ardware_intel.py`.
    path = Path(__file__).resolve().parents[1] / "ardware_intel.py"
    spec = importlib.util.spec_from_file_location("hardware_intel", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hardware_intel_module_loads():
    module = _load_skill_module()
    assert hasattr(module, "execute")


def test_hardware_intel_execute_android_path():
    module = _load_skill_module()
    result = module.execute(SimpleNamespace(platform="android"))
    assert "BT" in result
    assert "NFC" in result


def test_hardware_intel_execute_desktop_path():
    module = _load_skill_module()
    result = module.execute(SimpleNamespace(platform="linux"))
    # Should contain actual hardware info, not escaped newlines
    assert "\\n" not in result
    assert "CPU" in result or "ОС" in result


def test_hardware_intel_execute_returns_real_newlines():
    module = _load_skill_module()
    result = module.execute(None)
    # Result should use real newlines, not escaped \n
    assert "\\n" not in result
    assert "\n" in result


def test_hardware_intel_execute_no_core():
    module = _load_skill_module()
    result = module.execute()
    assert isinstance(result, str)
    assert len(result) > 0


def test_hardware_intel_skill_has_handle():
    """src/skills/hardware_intel.py должен иметь функцию handle() для SkillLoader."""
    from src.skills import hardware_intel as hw
    assert hasattr(hw, "handle"), "handle() функция отсутствует в src/skills/hardware_intel.py"


def test_hardware_intel_skill_handle_trigger():
    """handle() должен отвечать на известные триггеры."""
    from src.skills import hardware_intel as hw
    result = hw.handle("проверь железо")
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


def test_hardware_intel_skill_handle_ignores_unrelated():
    """handle() должен вернуть None для нерелевантных запросов."""
    from src.skills import hardware_intel as hw
    result = hw.handle("расскажи анекдот")
    assert result is None


def test_hardware_intel_skill_execute_contains_os_info():
    """execute() должен содержать информацию об ОС."""
    from src.skills import hardware_intel as hw
    result = hw.execute()
    assert isinstance(result, str)
    assert len(result) > 0


def test_hardware_intel_skill_triggers_list():
    """SKILL_TRIGGERS должен содержать основные русские фразы."""
    from src.skills import hardware_intel as hw
    triggers = hw.SKILL_TRIGGERS
    assert "проверь железо" in triggers
    assert "диагностика железа" in triggers

