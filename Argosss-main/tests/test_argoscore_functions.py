# tests/test_argoscore_functions.py
"""Tests for ArgosCore._argoscore_functions and its execute_intent triggers."""
from types import SimpleNamespace

import pytest

from src.core import ArgosCore


def _make_dummy_core(version="1.3.0"):
    """Build a minimal dummy that satisfies _argoscore_functions."""
    return SimpleNamespace(
        VERSION=version,
        quantum=object(),
        memory=object(),
        agent=object(),
        sensors=object(),
        skill_loader=object(),
        curiosity=object(),
        homeostasis=object(),
        tool_calling=object(),
        scheduler=object(),
        alerts=object(),
        vision=object(),
        p2p=None,
        iot_bridge=object(),
        industrial=object(),
        platform_admin=object(),
        smart_sys=object(),
        ha=object(),
        git_ops=object(),
        module_loader=object(),
        grist=object(),
        cloud_object_storage=object(),
        otg=object(),
        own_model=object(),
        ai_mode_label=lambda: "Auto",
        _argoscore_functions=ArgosCore._argoscore_functions,
    )


def test_argoscore_functions_contains_version():
    dummy = _make_dummy_core("1.3.0")
    result = ArgosCore._argoscore_functions(dummy)
    assert "1.3.0" in result


def test_argoscore_functions_heading():
    dummy = _make_dummy_core()
    result = ArgosCore._argoscore_functions(dummy)
    assert "ArgosCore" in result
    assert "ФУНКЦИИ" in result


def test_argoscore_functions_active_subsystems():
    dummy = _make_dummy_core()
    result = ArgosCore._argoscore_functions(dummy)
    assert "✅ активна" in result


def test_argoscore_functions_inactive_subsystem():
    dummy = _make_dummy_core()
    # p2p is None → should show as not loaded
    result = ArgosCore._argoscore_functions(dummy)
    assert "⚠️ не загружена" in result


def test_argoscore_functions_public_api_listed():
    dummy = _make_dummy_core()
    result = ArgosCore._argoscore_functions(dummy)
    assert "process(user_text)" in result
    assert "execute_intent(text, admin)" in result
    assert "say(text)" in result


def test_argoscore_functions_ai_mode_shown():
    dummy = _make_dummy_core()
    result = ArgosCore._argoscore_functions(dummy)
    assert "Auto" in result


# ── execute_intent trigger tests ───────────────────────────────────────────


def _make_execute_dummy():
    """Minimal dummy for execute_intent routing tests."""
    ns = SimpleNamespace(
        _argoscore_functions=lambda: "ARGOSCORE_FUNCTIONS_RESULT",
        _help=lambda: "HELP_RESULT",
        _homeostasis_block_heavy=False,
    )
    # Attach all attributes that execute_intent branches may touch
    for attr in (
        "quantum", "memory", "agent", "sensors", "skill_loader", "curiosity",
        "homeostasis", "tool_calling", "scheduler", "alerts", "vision", "p2p",
        "iot_bridge", "industrial", "platform_admin", "smart_sys", "ha",
        "git_ops", "module_loader", "grist", "cloud_object_storage", "otg",
        "own_model", "smart_profiles", "_smart_create_wizard", "operator_mode",
        "dag_manager", "marketplace", "mesh_net", "gateway_mgr", "homeostasis",
        "db",
    ):
        if not hasattr(ns, attr):
            setattr(ns, attr, None)
    return ns


@pytest.mark.parametrize("phrase", [
    "функции аргоскоре",
    "аргоскоре функции",
    "функции ядра",
    "проверь аргоскоре",
    "аргоскоре проверь",
    "возможности аргоскоре",
    "аргоскоре возможности",
    "что умеет аргоскоре",
    "argoscore функции",
    "argoscore возможности",
    "список функций аргоса",
    "функции argos",
    "функции аргоса",
    "список функций",
])
def test_execute_intent_argoscore_functions_trigger(phrase):
    dummy = _make_execute_dummy()
    result = ArgosCore.execute_intent(dummy, phrase, admin=None, flasher=None)
    assert result == "ARGOSCORE_FUNCTIONS_RESULT", (
        f"Phrase {phrase!r} did not trigger _argoscore_functions(); got: {result!r}"
    )
