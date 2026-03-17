from types import SimpleNamespace

from src.core import ArgosCore


def test_execute_intent_handles_typo_diagnostic_phrase():
    dummy = SimpleNamespace(
        _ai_modes_diagnostic=lambda: "ok",
    )
    result = ArgosCore.execute_intent(
        dummy,
        "ПОЗНАНИЕ ЛЮБОПЫТСТВО ДИОЛОГ",
        admin=None,
        flasher=None,
    )
    assert result == "ok"


def test_ai_modes_diagnostic_includes_learning_and_grist_state():
    dummy = SimpleNamespace(
        ai_mode_label=lambda: "Auto",
        own_model=SimpleNamespace(status=lambda: "🤖 model ok"),
        grist=SimpleNamespace(_configured=True),
        memory=object(),
        curiosity=SimpleNamespace(status=lambda: "👁️ curiosity ok"),
        context=object(),
    )
    text = ArgosCore._ai_modes_diagnostic(dummy)
    assert "Режим ИИ: Auto" in text
    assert "Обучение модели: 🤖 model ok" in text
    assert "Синхронизация знаний (ГОСТ P2P Grist): ✅" in text
    assert "Познание (память): ✅" in text
    assert "Любопытство: 👁️ curiosity ok" in text
    assert "Диалоговый контекст: ✅" in text
